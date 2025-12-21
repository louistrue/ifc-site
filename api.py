import asyncio
import os
import tempfile
from typing import Dict, Optional
from uuid import uuid4

import requests
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, root_validator

import combined_terrain

app = FastAPI(title="Site Boundaries Terrain API")


class GenerateRequest(BaseModel):
    egrid: Optional[str] = Field(None, description="Swiss cadastral EGRID identifier")
    center_x: Optional[float] = Field(
        None, description="Optional override for center easting (EPSG:2056)"
    )
    center_y: Optional[float] = Field(
        None, description="Optional override for center northing (EPSG:2056)"
    )
    radius: float = Field(
        500.0, gt=0, description="Radius of circular terrain area (meters)"
    )
    resolution: float = Field(
        10.0, gt=0, description="Grid resolution in meters (lower = more detail)"
    )
    densify: float = Field(
        0.5, gt=0, description="Site boundary densification interval (meters)"
    )
    attach_to_solid: bool = Field(
        False,
        description="Attach terrain to smoothed site solid edges (less bumpy)",
    )
    output_name: str = Field(
        "combined_terrain.ifc",
        description="Suggested filename for the generated IFC",
    )

    @root_validator
    def validate_location(cls, values):
        egrid = values.get("egrid")
        if not egrid:
            raise ValueError("An EGRID value is required for combined terrain generation.")
        return values


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
        output_path,
    )


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/generate")
async def generate_file(body: GenerateRequest):
    desired_name = _ensure_ifc_extension(body.output_name or "combined_terrain.ifc")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc")
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

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ifc")
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


@app.post("/jobs")
async def create_job(body: GenerateRequest):
    job_id = str(uuid4())
    output_name = _ensure_ifc_extension(body.output_name or "combined_terrain.ifc")

    async with job_lock:
        jobs[job_id] = JobRecord(output_name=output_name)

    asyncio.create_task(_execute_job(job_id, body))

    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
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


@app.get("/jobs/{job_id}/download")
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
