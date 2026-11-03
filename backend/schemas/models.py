"""Pydantic schemas for the StreamCore REST API and database records."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class DatabaseModel(BaseModel):
    """Common configuration for models populated from SQLite rows."""

    model_config = {"from_attributes": True}


class Area(DatabaseModel):
    area_id: str
    name: str
    sort_order: int = 0
    created_at: float
    updated_at: float


class AreaResponse(Area):
    camera_count: int = 0


class CameraMetadata(DatabaseModel):
    camera_id: str
    display_name: Optional[str] = None
    area_id: Optional[str] = None
    kind: str = "both"
    level: str = "standard"
    notes: Optional[str] = None
    created_at: float
    updated_at: float


class Camera(DatabaseModel):
    camera_id: str
    name: str
    uri: str
    codec: str = "h264"
    decoder: str = "auto"
    decoding_fps: Optional[float] = None
    status: str = "active"
    camera_metadata: Optional[dict[str, Any]] = None
    created_at: float
    updated_at: float


class InferenceEvent(DatabaseModel):
    event_id: str
    track_id: str
    track_session_id: str
    camera_id: str
    camera_name: Optional[str] = None
    event_type: str
    object_class: str
    started_at_utc: str
    ended_at_utc: Optional[str] = None
    duration_seconds: Optional[float] = None
    max_confidence: Optional[float] = None
    avg_confidence: Optional[float] = None
    description: Optional[str] = None
    snapshot_path: Optional[str] = None
    clip_path: Optional[str] = None
    clip_recorded: bool = False
    metadata: Optional[dict[str, Any]] = None
    created_at: float
    updated_at: float


class AppSetting(DatabaseModel):
    key: str
    value: str
    updated_at: float


class PublicUser(DatabaseModel):
    """User representation safe to return from API endpoints."""

    user_id: str
    username: str
    display_name: str = ""
    role: str = Field("operator", pattern="^(admin|operator|viewer)$")
    is_active: bool = True
    last_login_at: Optional[float] = None
    created_at: float
    updated_at: float


class Session(DatabaseModel):
    session_id: str
    user_id: str
    created_at: float
    last_seen_at: float
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogEntry(DatabaseModel):
    id: int
    user_id: Optional[str] = None
    action: str
    resource: Optional[str] = None
    detail: Optional[str] = None
    ip: Optional[str] = None
    created_at: float


class AuthCredentials(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=3, max_length=15)


class AuthSetupRequest(AuthCredentials):
    display_name: Optional[str] = Field(None, max_length=120)


class SignupRequest(AuthCredentials):
    display_name: Optional[str] = Field(None, max_length=120)
    role: str = Field("operator", pattern="^(admin|operator|viewer)$")


class CameraRegisterRequest(BaseModel):
    camera_id: Optional[str] = None
    name: Optional[str] = None
    rtsp_url: Optional[str] = None
    uri: Optional[str] = None
    codec: str = "h264"
    decoder: str = "auto"
    decoding_fps: Optional[float] = None
    status: str = "active"
    camera_metadata: Optional[dict[str, Any]] = None
    live_path: Optional[str] = None


class CameraMetadataRequest(BaseModel):
    """Partial update of operator-editable camera metadata."""

    camera_id: Optional[str] = Field(None, min_length=1, max_length=120)
    name: Optional[str] = Field(None, max_length=120)
    uri: Optional[str] = Field(None, max_length=2048)
    rtsp_url: Optional[str] = Field(None, max_length=2048)
    codec: Optional[str] = Field(None, max_length=40)
    decoder: Optional[str] = Field(None, max_length=80)
    decoding_fps: Optional[float] = Field(None, gt=0)
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

