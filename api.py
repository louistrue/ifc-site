import asyncio
import os
import tempfile
from typing import Dict, Optional
from uuid import uuid4

import requests
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict, model_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

import combined_terrain

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Site Boundaries Terrain API",
    # Disable docs in production (optional - set via env var)
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
    redoc_url="/redoc" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# CORS - configure allowed origins (restrict in production)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # Set True only if needed
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Trusted Host middleware (prevents host header attacks)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
if ALLOWED_HOSTS != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


class GenerateRequest(BaseModel):
    egrid: str = Field(
        ...,
        min_length=10,
        max_length=20,
        pattern=r"^CH[0-9]{9,18}$",  # Swiss EGRID format validation
        description="Swiss cadastral EGRID identifier (required)",
        example="CH999979659148"
    )
    center_x: Optional[float] = Field(
        None,
        description="Optional override for center easting (EPSG:2056). If not provided, uses parcel centroid.",
        example=None
    )
    center_y: Optional[float] = Field(
        None,
        description="Optional override for center northing (EPSG:2056). If not provided, uses parcel centroid.",
        example=None
    )
    radius: float = Field(
        500.0,
        gt=0,
        le=2000,  # Maximum 2km radius to prevent abuse
        description="Radius of circular terrain area (meters)",
        example=500.0
    )
    resolution: float = Field(
        10.0,
        ge=5,  # Minimum 5m to prevent excessive API calls
        le=100,
        description="Grid resolution in meters (lower = more detail, but slower)",
        example=10.0
    )
    densify: float = Field(
        0.5,
        ge=0.1,
        le=10.0,
        description="Site boundary densification interval (meters). Lower values create more boundary points.",
        example=0.5
    )
    attach_to_solid: bool = Field(
        False,
        description="Attach terrain to smoothed site solid edges (less bumpy transition)",
        example=False
    )
    include_terrain: bool = Field(
        True,
        description="Include surrounding terrain mesh with cutout",
        example=True
    )
    include_site_solid: bool = Field(
        True,
        description="Include site boundary solid",
        example=True
    )
    output_name: str = Field(
        "combined_terrain.ifc",
        description="Suggested filename for the generated IFC file",
        example="combined_terrain.ifc"
    )

    @model_validator(mode='after')
    def validate_at_least_one_component(self):
        if not self.include_terrain and not self.include_site_solid:
            raise ValueError("At least one of include_terrain or include_site_solid must be True")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "egrid": "CH999979659148",
                "radius": 500.0,
                "resolution": 10.0,
                "densify": 0.5,
                "attach_to_solid": False,
                "include_terrain": True,
                "include_site_solid": True,
                "output_name": "combined_terrain.ifc"
            }
        }
    )


class JobRecord:
    def __init__(self, output_name: str):
        self.status: str = "pending"
        self.output_name: str = output_name
        self.path: Optional[str] = None
        self.error: Optional[str] = None


jobs: Dict[str, JobRecord] = {}
job_lock = asyncio.Lock()


def _ensure_ifc_extension(name: str) -> str:
    if not name.lower().endswith(".ifc"):
        return f"{name}.ifc"
    return name


def _cleanup_file(path: str):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _map_exception_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, requests.Timeout):
        return HTTPException(status_code=504, detail="Upstream request timed out.")
    if isinstance(exc, requests.HTTPError):
        return HTTPException(status_code=502, detail="Upstream service error.")
    if isinstance(exc, requests.RequestException):
        return HTTPException(status_code=502, detail="Upstream request failed.")
    return HTTPException(status_code=500, detail="Internal server error.")


async def _run_generation(request: GenerateRequest, output_path: str):
    return await run_in_threadpool(
        combined_terrain.run_combined_terrain_workflow,
        request.egrid,
        request.center_x,
        request.center_y,
        request.radius,
        request.resolution,
        request.densify,
        request.attach_to_solid,
        request.include_terrain,
        request.include_site_solid,
        output_path,
    )


@app.get(
    "/health",
    summary="Health check",
    description="Check if the API service is running and healthy",
    response_description="Health status"
)
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/generate",
    summary="Generate IFC file immediately",
    description="Generate a combined terrain IFC file synchronously. The file is streamed back as a download.",
    response_description="IFC file download",
    responses={
        200: {
            "description": "Successful response - IFC file download",
            "content": {"application/octet-stream": {}}
        },
        400: {"description": "Bad request - Invalid EGRID or generation failed"},
        422: {"description": "Validation error - Invalid request parameters"},
        429: {"description": "Rate limit exceeded"},
        502: {"description": "Upstream service error"},
        504: {"description": "Request timeout"}
    }
)
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def generate_file(request: Request, body: GenerateRequest):
    desired_name = _ensure_ifc_extension(body.output_name or "combined_terrain.ifc")
    # Use TMPDIR if set (for Docker container security)
    tmpdir = os.getenv("TMPDIR", tempfile.gettempdir())
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc", dir=tmpdir)
    tmp_path = tmp.name
    tmp.close()

    try:
        await _run_generation(body, tmp_path)
    except Exception as exc:
        _cleanup_file(tmp_path)
        raise _map_exception_to_http(exc)

    headers = {
        "Content-Disposition": f'attachment; filename="{desired_name}"'
    }
    background = BackgroundTasks()
    background.add_task(_cleanup_file, tmp_path)
    return StreamingResponse(
        open(tmp_path, "rb"),
        media_type="application/octet-stream",
        headers=headers,
        background=background,
    )


async def _execute_job(job_id: str, request: GenerateRequest):
    async with job_lock:
        job = jobs[job_id]
        job.status = "running"

    # Use TMPDIR if set (for Docker container security)
    tmpdir = os.getenv("TMPDIR", tempfile.gettempdir())
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc", dir=tmpdir)
    tmp_path = tmp.name
    tmp.close()

    try:
        await _run_generation(request, tmp_path)
    except Exception as exc:
        detail = _map_exception_to_http(exc).detail
        async with job_lock:
            job = jobs[job_id]
            job.status = "failed"
            job.error = detail
        _cleanup_file(tmp_path)
        return

    async with job_lock:
        job = jobs[job_id]
        job.status = "completed"
        job.path = tmp_path


@app.post(
    "/jobs",
    summary="Create background job",
    description="Create a background job to generate an IFC file asynchronously. Returns a job_id that can be used to check status and download the result.",
    response_description="Job creation response",
    responses={
        200: {"description": "Job created successfully"},
        422: {"description": "Validation error - Invalid request parameters"},
        429: {"description": "Rate limit exceeded"}
    }
)
@limiter.limit("20/minute")  # 20 job creations per minute per IP
async def create_job(request: Request, body: GenerateRequest):
    job_id = str(uuid4())
    output_name = _ensure_ifc_extension(body.output_name or "combined_terrain.ifc")

    async with job_lock:
        jobs[job_id] = JobRecord(output_name=output_name)

    asyncio.create_task(_execute_job(job_id, body))

    return {"job_id": job_id}


@app.get(
    "/jobs/{job_id}",
    summary="Get job status",
    description="Check the status of a background job. Returns status (pending/running/completed/failed/expired) and download URL when ready.",
    response_description="Job status response",
    responses={
        200: {"description": "Job status retrieved"},
        404: {"description": "Job not found"}
    }
)
async def job_status(job_id: str):
    async with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        response = {
            "status": job.status,
        }
        download_available = (
            job.status == "completed" and job.path and os.path.exists(job.path)
        )
        if download_available:
            response["download_url"] = f"/jobs/{job_id}/download"
            response["output_name"] = job.output_name
        if job.error:
            response["error"] = job.error
    return JSONResponse(response)


@app.get(
    "/jobs/{job_id}/download",
    summary="Download completed job",
    description="Download the IFC file generated by a completed job. The file is streamed as a download and the job is marked as expired.",
    response_description="IFC file download",
    responses={
        200: {
            "description": "Successful response - IFC file download",
            "content": {"application/octet-stream": {}}
        },
        404: {"description": "Job not found"},
        409: {"description": "Job is not ready (not completed yet)"},
        410: {"description": "Job output expired"}
    }
)
async def download_job(job_id: str):
    async with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job.status != "completed" or not job.path:
            raise HTTPException(status_code=409, detail="Job is not ready.")
        path = job.path
        output_name = job.output_name

    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Job output expired.")

    headers = {
        "Content-Disposition": f'attachment; filename="{output_name}"'
    }
    background = BackgroundTasks()
    background.add_task(_cleanup_file, path)
    async with job_lock:
        job = jobs.get(job_id)
        if job:
            job.path = None
            job.status = "expired"
    return StreamingResponse(
        open(path, "rb"),
        media_type="application/octet-stream",
        headers=headers,
        background=background,
    )
