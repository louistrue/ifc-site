import asyncio
import os
import tempfile
import time
from typing import Dict, Optional, Set
from uuid import uuid4

import requests
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from . import terrain_with_site

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
        
        # Conditionally set CSP: relaxed for docs endpoints, strict otherwise
        enable_docs = os.getenv("ENABLE_DOCS", "true").lower() == "true"
        if enable_docs and request.url.path in ["/docs", "/redoc", "/openapi.json"]:
            # Allow CDN resources for Swagger UI and ReDoc
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https:"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# CORS - configure allowed origins (restrict in production)
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
# Strip whitespace from origins
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS if origin.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # Set True only if needed
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Origin", "X-Requested-With"],
    expose_headers=["X-GLTF-Available", "X-Texture-Available", "X-Additional-Files-Available"],
)

# Trusted Host middleware (prevents host header attacks)
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
if ALLOWED_HOSTS != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


class GenerateRequest(BaseModel):
    # Input: Either egrid or address (at least one required)
    egrid: Optional[str] = Field(
        None,
        min_length=10,
        max_length=20,
        pattern=r"^CH[0-9]{9,18}$",  # Swiss EGRID format validation
        description="Swiss cadastral EGRID identifier (provide either egrid or address)"
    )
    address: Optional[str] = Field(
        None,
        min_length=3,
        max_length=200,
        description="Swiss address to resolve to EGRID (provide either egrid or address)"
    )

    # Location overrides
    center_x: Optional[float] = Field(
        None,
        description="Optional override for center easting (EPSG:2056). If not provided, uses parcel centroid."
    )
    center_y: Optional[float] = Field(
        None,
        description="Optional override for center northing (EPSG:2056). If not provided, uses parcel centroid."
    )

    # Terrain options
    include_terrain: bool = Field(
        True,
        description="Include surrounding terrain mesh with cutout"
    )
    radius: float = Field(
        500.0,
        gt=0,
        le=2000,  # Maximum 2km radius to prevent abuse
        description="Radius of circular terrain area (meters)"
    )
    resolution: float = Field(
        10.0,
        ge=5,  # Minimum 5m to prevent excessive API calls
        le=100,
        description="Grid resolution in meters (lower = more detail, but slower)"
    )
    attach_to_solid: bool = Field(
        False,
        description="Attach terrain to smoothed site solid edges (less bumpy transition)"
    )

    # Site solid options
    include_site_solid: bool = Field(
        True,
        description="Include site boundary solid"
    )
    densify: float = Field(
        2.0,  # Aligned with CLI default
        ge=0.1,
        le=10.0,
        description="Site boundary densification interval (meters). Lower values create more boundary points."
    )

    # Road options
    include_roads: bool = Field(
        False,
        description="Include roads in the model"
    )
    road_buffer: float = Field(
        100.0,
        ge=0,
        le=500,
        description="Buffer distance for road search (meters)"
    )
    road_recess: float = Field(
        0.15,
        ge=0,
        le=1.0,
        description="Depth to recess roads into terrain (meters)"
    )
    roads_as_separate_elements: bool = Field(
        False,
        description="Create roads as separate IFC elements instead of embedding in terrain"
    )

    # Forest options
    include_forest: bool = Field(
        False,
        description="Include forest/vegetation in the model"
    )
    forest_spacing: float = Field(
        20.0,
        ge=5,
        le=100,
        description="Spacing between forest sample points (meters)"
    )
    forest_threshold: float = Field(
        30.0,
        ge=0,
        le=100,
        description="Minimum forest coverage percentage to place tree (0-100)"
    )

    # Water options
    include_water: bool = Field(
        False,
        description="Include water features (lakes, rivers) in the model"
    )

    # Building options
    include_buildings: bool = Field(
        False,
        description="Include buildings from CityGML data"
    )

    # Railway options
    include_railways: bool = Field(
        False,
        description="Include railway tracks in the model"
    )

    # Bridge options
    include_bridges: bool = Field(
        False,
        description="Include bridges in the model (experimental)"
    )

    # Satellite imagery options
    include_satellite_overlay: bool = Field(
        False,
        description="Include satellite imagery texture overlay"
    )
    embed_imagery: bool = Field(
        True,
        description="Embed imagery in IFC file"
    )
    imagery_resolution: float = Field(
        0.5,
        ge=0.1,
        le=5.0,
        description="Imagery resolution in meters per pixel"
    )
    imagery_year: Optional[int] = Field(
        None,
        ge=2000,
        le=2030,
        description="Year for historical imagery (default: current)"
    )

    # Export options
    export_gltf: Optional[bool] = Field(
        None,
        description="Export glTF/GLB file alongside IFC (default: auto-enable if imagery enabled)"
    )
    apply_texture_to_buildings: Optional[bool] = Field(
        None,
        description="Apply satellite texture to buildings (default: auto if imagery enabled)"
    )

    # Output
    output_name: str = Field(
        "combined_terrain.ifc",
        description="Suggested filename for the generated IFC file"
    )

    # Convenience flag
    include_all: bool = Field(
        False,
        description="Enable all features: roads, forest, water, buildings, railways, satellite imagery (excludes bridges)"
    )

    @field_validator('egrid', 'address', mode='before')
    @classmethod
    def empty_string_to_none(cls, v):
        """Convert empty strings to None to avoid min_length validation errors."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode='after')
    def validate_request(self):
        # Require either egrid or address
        if not self.egrid and not self.address:
            raise ValueError("Either 'egrid' or 'address' must be provided")

        # Require at least one component
        if not self.include_terrain and not self.include_site_solid:
            raise ValueError("At least one of include_terrain or include_site_solid must be True")

        # Apply include_all flag
        if self.include_all:
            self.include_roads = True
            self.include_forest = True
            self.include_water = True
            self.include_buildings = True
            self.include_railways = True
            self.include_satellite_overlay = True
            # Note: bridges excluded from include_all (experimental)

        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "description": "Basic generation with EGRID",
                    "value": {
                        "egrid": "CH999979659148",
                        "radius": 500.0,
                        "resolution": 10.0,
                        "output_name": "site_terrain.ifc"
                    }
                },
                {
                    "description": "Generation with address and all features",
                    "value": {
                        "address": "Bundesplatz 3, Bern",
                        "include_all": True,
                        "radius": 300.0,
                        "output_name": "federal_palace.ifc"
                    }
                },
                {
                    "description": "Custom feature selection",
                    "value": {
                        "egrid": "CH999979659148",
                        "include_roads": True,
                        "include_buildings": True,
                        "include_water": True,
                        "include_satellite_overlay": True,
                        "export_gltf": True,
                        "radius": 400.0
                    }
                }
            ]
        }
    )


class JobRecord:
    def __init__(self, output_name: str, has_gltf: bool = False):
        self.status: str = "pending"
        self.output_name: str = output_name
        self.path: Optional[str] = None
        self.gltf_path: Optional[str] = None  # Path to .glb file if generated
        self.texture_path: Optional[str] = None  # Path to texture file if generated
        self.has_gltf: bool = has_gltf
        self.error: Optional[str] = None
        self.created_at: float = time.time()
        self.finished_at: Optional[float] = None


jobs: Dict[str, JobRecord] = {}
job_lock = asyncio.Lock()
_background_tasks: Set[asyncio.Task] = set()

# Configuration constants for job cleanup (can be overridden in tests)
JOB_TTL_SECONDS = float(os.getenv("JOB_TTL_SECONDS", "86400"))  # 24 hours default
JOB_MAX_COUNT = int(os.getenv("JOB_MAX_COUNT", "1000"))  # Max stored jobs
CLEANUP_INTERVAL_SECONDS = float(os.getenv("CLEANUP_INTERVAL_SECONDS", "3600"))  # 1 hour default


def _ensure_ifc_extension(name: str) -> str:
    if not name.lower().endswith(".ifc"):
        return f"{name}.ifc"
    return name


def _get_gltf_path(ifc_path: str) -> str:
    """Get the expected glTF path from an IFC path."""
    base = ifc_path.rsplit('.', 1)[0] if '.' in ifc_path else ifc_path
    return f"{base}.glb"


def _get_texture_path(ifc_path: str) -> str:
    """Get the expected texture path from an IFC path."""
    base = ifc_path.rsplit('.', 1)[0] if '.' in ifc_path else ifc_path
    return f"{base}_texture.jpg"


def _should_have_gltf(request: GenerateRequest) -> bool:
    """Determine if glTF should be generated based on request parameters."""
    if request.export_gltf is True:
        return True
    if request.export_gltf is False:
        return False
    # Auto-enable if satellite imagery is enabled
    return request.include_satellite_overlay


def _cleanup_file(path: str):
    """Clean up a file"""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


async def _cleanup_file_and_update_job(path: str, job_id: str):
    """Clean up a file and update job state to expired.

    NOTE: This is no longer used for download cleanup - files are now kept
    until TTL expiration to support multiple downloads.
    """
    _cleanup_file(path)
    async with job_lock:
        job = jobs.get(job_id)
        if job:
            job.path = None
            job.status = "expired"


def _cleanup_job_files(job: JobRecord):
    """Clean up all files associated with a job."""
    if job.path and os.path.exists(job.path):
        try:
            os.remove(job.path)
        except (FileNotFoundError, OSError):
            pass
    if job.gltf_path and os.path.exists(job.gltf_path):
        try:
            os.remove(job.gltf_path)
        except (FileNotFoundError, OSError):
            pass
    if job.texture_path and os.path.exists(job.texture_path):
        try:
            os.remove(job.texture_path)
        except (FileNotFoundError, OSError):
            pass


def _map_exception_to_http(exc: Exception) -> HTTPException:
    """Map exceptions to HTTP exceptions, preserving traceback context"""
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, requests.Timeout):
        return HTTPException(status_code=504, detail="Upstream request timed out.")
    if isinstance(exc, requests.HTTPError):
        return HTTPException(status_code=502, detail="Upstream service error.")
    if isinstance(exc, requests.RequestException):
        return HTTPException(status_code=502, detail="Upstream request failed.")
    return HTTPException(status_code=500, detail="Internal server error.")


def _file_stream_generator(file_path: str):
    """Generator that safely streams a file and ensures it's closed"""
    file_handle = None
    try:
        file_handle = open(file_path, "rb")
        while True:
            chunk = file_handle.read(8192)  # 8KB chunks
            if not chunk:
                break
            yield chunk
    finally:
        if file_handle:
            file_handle.close()


async def _cleanup_old_jobs():
    """Background task to clean up old jobs based on TTL and max count"""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            
            async with job_lock:
                current_time = time.time()
                jobs_to_remove = []
                
                # First pass: Remove jobs older than TTL
                for job_id, job in jobs.items():
                    if job.finished_at and (current_time - job.finished_at) > JOB_TTL_SECONDS:
                        jobs_to_remove.append(job_id)
                    elif not job.finished_at and (current_time - job.created_at) > JOB_TTL_SECONDS:
                        # Also remove very old pending/running jobs (stuck jobs)
                        jobs_to_remove.append(job_id)
                
                # Remove TTL-expired jobs
                for job_id in jobs_to_remove:
                    job = jobs[job_id]
                    _cleanup_job_files(job)
                    del jobs[job_id]
                
                # Second pass: If still over max count, remove oldest finished jobs
                if len(jobs) > JOB_MAX_COUNT:
                    finished_jobs = [
                        (job_id, job) 
                        for job_id, job in jobs.items() 
                        if job.finished_at is not None
                    ]
                    # Sort by finished_at, oldest first
                    finished_jobs.sort(key=lambda x: x[1].finished_at or 0)
                    
                    excess_count = len(jobs) - JOB_MAX_COUNT
                    for job_id, job in finished_jobs[:excess_count]:
                        _cleanup_job_files(job)
                        del jobs[job_id]
                        
        except Exception as e:
            # Log error but continue cleanup loop
            print(f"Error in job cleanup task: {e}")


async def _run_generation(request: GenerateRequest, output_path: str):
    """Run the terrain generation workflow with all parameters."""
    return await run_in_threadpool(
        terrain_with_site.run_combined_terrain_workflow,
        egrid=request.egrid,
        address=request.address,
        center_x=request.center_x,
        center_y=request.center_y,
        radius=request.radius,
        resolution=request.resolution,
        densify=request.densify,
        attach_to_solid=request.attach_to_solid,
        include_terrain=request.include_terrain,
        include_site_solid=request.include_site_solid,
        include_roads=request.include_roads,
        include_forest=request.include_forest,
        include_water=request.include_water,
        include_buildings=request.include_buildings,
        include_railways=request.include_railways,
        include_bridges=request.include_bridges,
        road_buffer_m=request.road_buffer,
        forest_spacing=request.forest_spacing,
        forest_threshold=request.forest_threshold,
        road_recess_depth=request.road_recess,
        embed_roads_in_terrain=not request.roads_as_separate_elements,
        output_path=output_path,
        include_satellite_overlay=request.include_satellite_overlay,
        embed_imagery=request.embed_imagery,
        imagery_resolution=request.imagery_resolution,
        imagery_year=request.imagery_year,
        export_gltf=request.export_gltf,
        apply_texture_to_buildings=request.apply_texture_to_buildings,
    )


@app.on_event("startup")
async def startup_event():
    """Start background cleanup task on application startup"""
    cleanup_task = asyncio.create_task(_cleanup_old_jobs())
    _background_tasks.add(cleanup_task)
    cleanup_task.add_done_callback(_background_tasks.discard)


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel background tasks on shutdown"""
    for task in _background_tasks:
        task.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)


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
    description="""Generate a combined terrain IFC file synchronously. The file is streamed back as a download.

**Note:** This endpoint returns only the IFC file. If you enable satellite imagery (include_satellite_overlay=true),
glTF and texture files will also be generated but not returned by this endpoint. Check the response headers
(X-GLTF-Available, X-Texture-Available) to see if additional files were generated. Use the `/jobs` endpoint
to access all generated files including glTF and textures.""",
    response_description="IFC file download",
    responses={
        200: {
            "description": "Successful response - IFC file download. Check X-GLTF-Available and X-Texture-Available headers.",
            "content": {"application/octet-stream": {}}
        },
        400: {"description": "Bad request - Invalid EGRID/address or generation failed"},
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
        _cleanup_file(_get_gltf_path(tmp_path))
        _cleanup_file(_get_texture_path(tmp_path))
        raise _map_exception_to_http(exc) from exc

    # Check if glTF/texture files were generated
    gltf_path = _get_gltf_path(tmp_path)
    texture_path = _get_texture_path(tmp_path)
    gltf_available = os.path.exists(gltf_path)
    texture_available = os.path.exists(texture_path)

    headers = {
        "Content-Disposition": f'attachment; filename="{desired_name}"'
    }

    # Add headers to inform client about additional files
    if gltf_available or texture_available:
        headers["X-Additional-Files-Available"] = "true"
        if gltf_available:
            headers["X-GLTF-Available"] = "true"
        if texture_available:
            headers["X-Texture-Available"] = "true"
        # Note: Use the /jobs endpoint to download glTF and texture files

    background = BackgroundTasks()
    background.add_task(_cleanup_file, tmp_path)
    background.add_task(_cleanup_file, gltf_path)
    background.add_task(_cleanup_file, texture_path)
    return StreamingResponse(
        _file_stream_generator(tmp_path),
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
            job.finished_at = time.time()
        _cleanup_file(tmp_path)
        # Also cleanup any glTF/texture files that might have been created
        _cleanup_file(_get_gltf_path(tmp_path))
        _cleanup_file(_get_texture_path(tmp_path))
        return

    async with job_lock:
        job = jobs[job_id]
        job.status = "completed"
        job.path = tmp_path
        job.finished_at = time.time()

        # Check for glTF and texture files
        gltf_path = _get_gltf_path(tmp_path)
        texture_path = _get_texture_path(tmp_path)
        if os.path.exists(gltf_path):
            job.gltf_path = gltf_path
            job.has_gltf = True
        if os.path.exists(texture_path):
            job.texture_path = texture_path


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

    task = asyncio.create_task(_execute_job(job_id, body))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"job_id": job_id}


@app.get(
    "/jobs/{job_id}",
    summary="Get job status",
    description="Check the status of a background job. Returns status (pending/running/completed/failed/expired) and download URLs when ready.",
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

            # Include glTF download info if available
            if job.gltf_path and os.path.exists(job.gltf_path):
                response["gltf_download_url"] = f"/jobs/{job_id}/download/gltf"
                base_name = job.output_name.rsplit('.', 1)[0] if '.' in job.output_name else job.output_name
                response["gltf_output_name"] = f"{base_name}.glb"

            # Include texture download info if available
            if job.texture_path and os.path.exists(job.texture_path):
                response["texture_download_url"] = f"/jobs/{job_id}/download/texture"
                base_name = job.output_name.rsplit('.', 1)[0] if '.' in job.output_name else job.output_name
                response["texture_output_name"] = f"{base_name}_texture.jpg"

        if job.error:
            response["error"] = job.error
    return JSONResponse(response)


@app.get(
    "/jobs/{job_id}/download",
    summary="Download completed job",
    description="Download the IFC file generated by a completed job. The file can be downloaded multiple times until the job expires (TTL-based cleanup).",
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
    # Don't delete file after download - allow multiple downloads
    # Files are cleaned up by TTL-based background task instead
    return StreamingResponse(
        _file_stream_generator(path),
        media_type="application/octet-stream",
        headers=headers,
    )


@app.get(
    "/jobs/{job_id}/download/gltf",
    summary="Download glTF file",
    description="Download the glTF/GLB file generated by a completed job (if available). The glTF file includes satellite imagery textures.",
    response_description="GLB file download",
    responses={
        200: {
            "description": "Successful response - GLB file download",
            "content": {"model/gltf-binary": {}}
        },
        404: {"description": "Job not found or glTF not available"},
        409: {"description": "Job is not ready (not completed yet)"},
        410: {"description": "Job output expired"}
    }
)
async def download_job_gltf(job_id: str):
    async with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job.status != "completed":
            raise HTTPException(status_code=409, detail="Job is not ready.")
        if not job.gltf_path:
            raise HTTPException(status_code=404, detail="glTF file not available for this job.")
        path = job.gltf_path
        base_name = job.output_name.rsplit('.', 1)[0] if '.' in job.output_name else job.output_name
        output_name = f"{base_name}.glb"

    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="glTF output expired.")

    headers = {
        "Content-Disposition": f'attachment; filename="{output_name}"'
    }
    # Don't delete file after download - allow multiple downloads
    # Files are cleaned up by TTL-based background task instead
    return StreamingResponse(
        _file_stream_generator(path),
        media_type="model/gltf-binary",
        headers=headers,
    )


@app.get(
    "/jobs/{job_id}/download/texture",
    summary="Download texture file",
    description="Download the satellite imagery texture file generated by a completed job (if available).",
    response_description="JPEG texture file download",
    responses={
        200: {
            "description": "Successful response - JPEG texture download",
            "content": {"image/jpeg": {}}
        },
        404: {"description": "Job not found or texture not available"},
        409: {"description": "Job is not ready (not completed yet)"},
        410: {"description": "Job output expired"}
    }
)
async def download_job_texture(job_id: str):
    async with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job.status != "completed":
            raise HTTPException(status_code=409, detail="Job is not ready.")
        if not job.texture_path:
            raise HTTPException(status_code=404, detail="Texture file not available for this job.")
        path = job.texture_path
        base_name = job.output_name.rsplit('.', 1)[0] if '.' in job.output_name else job.output_name
        output_name = f"{base_name}_texture.jpg"

    if not os.path.exists(path):
        raise HTTPException(status_code=410, detail="Texture output expired.")

    headers = {
        "Content-Disposition": f'attachment; filename="{output_name}"'
    }
    # Don't delete file after download - allow multiple downloads
    # Files are cleaned up by TTL-based background task instead
    return StreamingResponse(
        _file_stream_generator(path),
        media_type="image/jpeg",
        headers=headers,
    )
