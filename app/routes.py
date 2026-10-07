"""API route definitions for the Geospatial File Measurement API."""

import os
import shutil
import tempfile
import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.models import FileInfoResponse, MeasurementsResponse, UploadResponse
from app.service import files_db, process_file_task

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", response_model=UploadResponse, status_code=202)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:
    """
    Upload a geospatial file (.zip Shapefile or .kml) for async processing.

    Returns a file ID that can be polled via ``GET /api/files/{id}/``.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in (".zip", ".kml"):
        raise HTTPException(
            status_code=422,
            detail="Unsupported file format. Please upload .zip (Shapefile) or .kml",
        )

    file_id = str(uuid.uuid4())
    temp_path = os.path.join(tempfile.gettempdir(), f"{file_id}{ext}")

    try:
        with open(temp_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc
    finally:
        file.file.close()

    # Initialise the DB record before the background task runs.
    files_db[file_id] = {
        "id": file_id,
        "filename": file.filename,
        "status": "PROCESSING",
        "feature_count": 0,
        "crs": None,
        "features": [],
    }

    background_tasks.add_task(
        process_file_task, file_id, temp_path, file.filename, ext
    )

    return UploadResponse(
        message="File uploaded successfully", id=file_id, status="PROCESSING"
    )


@router.get("/{file_id}/", response_model=FileInfoResponse)
async def get_file_info(file_id: str) -> FileInfoResponse:
    """Return metadata / status for the given file ID."""
    if file_id not in files_db:
        raise HTTPException(status_code=404, detail="File not found")

    data = files_db[file_id]
    return FileInfoResponse(
        id=data["id"],
        filename=data["filename"],
        feature_count=data["feature_count"],
        crs=data.get("crs"),
        status=data["status"],
        error=data.get("error"),
    )


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
async def get_file_measurements(file_id: str):
    """
    Return the full feature list with measurements once processing is complete.

    If the file is still processing or has failed, a descriptive response is
    returned with HTTP 200 so the frontend can keep polling gracefully.
    """
    if file_id not in files_db:
        raise HTTPException(status_code=404, detail="File not found")

    data = files_db[file_id]
    if data["status"] != "COMPLETED":
        return {
            "status": data["status"],
            "message": "File is not yet processed or failed",
            "error": data.get("error"),
        }

    return {"id": data["id"], "features": data["features"]}
