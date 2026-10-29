"""Pydantic schemas for StreamCore REST API."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class CameraRegisterRequest(BaseModel):
    camera_id: Optional[str] = None
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    uri: Optional[str] = None
    codec: str = "h264"
    decoder: str = "auto"
    live_path: Optional[str] = None


class CameraMetadataRequest(BaseModel):
    """Partial update of operator-editable camera metadata."""

    display_name: Optional[str] = Field(None, max_length=120)
    area_id: Optional[str] = None
    kind: Optional[str] = None
    level: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=2000)


class AreaCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    sort_order: int = 0


class AreaUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    sort_order: Optional[int] = None


class CameraAnalyzeRequest(BaseModel):
    sample_count: int = 20
    sample_duration_seconds: float = 8.0
    force_fresh: bool = False


class VisualSearchRequest(BaseModel):
    query: str = ""
    camera_id: Optional[str] = None
    start: Optional[str] = None
    start_utc: Optional[str] = None
    end: Optional[str] = None
    end_utc: Optional[str] = None
    top_k: int = 2


class ApplyCapabilitiesRequest(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    expected_version: Optional[int] = None
    configurations: Optional[dict[str, Any]] = None


class UpdateZonesRequest(BaseModel):
    zones: list[dict[str, Any]] = Field(default_factory=list)
    expected_version: Optional[int] = None


class UpdateLinesRequest(BaseModel):
    lines: list[dict[str, Any]] = Field(default_factory=list)
    expected_version: Optional[int] = None


class UpdateRulesRequest(BaseModel):
    rules: list[dict[str, Any]] = Field(default_factory=list)
    expected_version: Optional[int] = None

