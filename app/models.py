"""Pydantic models / shared type definitions for the Geospatial API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class MeasurementResult(BaseModel):
    """Measurement data for a single geometry."""

    type: str
    value: float
    unit: Optional[str] = None
    message: Optional[str] = None


class FeatureResult(BaseModel):
    """Processed data for a single geospatial feature."""

    feature_id: str
    geometry_type: str
    geometry: Dict[str, Any]
    crs: str
    properties: Dict[str, Optional[str]]
    measurement: MeasurementResult


class FileRecord(BaseModel):
    """In-memory record for an uploaded file."""

    id: str
    filename: str
    status: str  # PROCESSING | COMPLETED | FAILED
    feature_count: int = 0
    crs: Optional[str] = None
    features: List[FeatureResult] = []
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Upload / response schemas
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    message: str
    id: str
    status: str


class FileInfoResponse(BaseModel):
    id: str
    filename: str
    feature_count: int
    crs: Optional[str]
    status: str
    error: Optional[str] = None


class MeasurementsResponse(BaseModel):
    id: str
    features: List[FeatureResult]
