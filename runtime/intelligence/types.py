from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import time
from typing import Any


class AnchorType(StrEnum):
    BOTTOM_CENTER = "BOTTOM_CENTER"
    CENTER = "CENTER"
    CUSTOM = "CUSTOM"


class ZoneState(StrEnum):
    OUTSIDE = "OUTSIDE"
    PENDING_ENTER = "PENDING_ENTER"
    INSIDE = "INSIDE"
    PENDING_EXIT = "PENDING_EXIT"


class CrossingDirection(StrEnum):
    IN = "IN"
    OUT = "OUT"
    BIDIRECTIONAL = "BIDIRECTIONAL"


class RuleType(StrEnum):
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_ENTRY = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    LINE_CROSSING = "LINE_CROSSING"
    LINE_CROSS = "LINE_CROSSING"
    DWELL_THRESHOLD = "DWELL_THRESHOLD"
    DWELL_TIME = "DWELL_THRESHOLD"
    VISIBLE_OCCUPANCY_THRESHOLD = "VISIBLE_OCCUPANCY_THRESHOLD"
    OCCUPANCY_THRESHOLD = "VISIBLE_OCCUPANCY_THRESHOLD"
    FLOW_OCCUPANCY_THRESHOLD = "FLOW_OCCUPANCY_THRESHOLD"


class EventStatus(StrEnum):
    OPEN = "OPEN"
    UPDATED = "UPDATED"
    CLOSED = "CLOSED"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class Point:
    """Normalized 2D point [0.0, 1.0]."""
    x: float
    y: float

    def __iter__(self):
        yield self.x
        yield self.y

    def __getitem__(self, idx: int) -> float:
        if idx == 0:
            return self.x
        elif idx == 1:
            return self.y
        raise IndexError("Point index out of range")

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 6), "y": round(self.y, 6)}

    @classmethod
    def from_dict(cls, data: Any) -> Point:
        if isinstance(data, (list, tuple)):
            return cls(x=float(data[0]), y=float(data[1]))
        if isinstance(data, Point):
            return data
        return cls(x=float(data["x"]), y=float(data["y"]))


class PolygonZone:
    def __init__(
        self,
        zone_id: str,
        name_or_camera: str = "",
        polygon_or_name: Any = None,
        polygon: list[Point] | None = None,
        camera_id: str = "",
        applicable_classes: list[str] | None = None,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.zone_id = str(zone_id)
        if isinstance(polygon_or_name, list):
            self.name = str(name_or_camera or zone_id)
            self.polygon = [Point.from_dict(p) for p in polygon_or_name]
            self.camera_id = str(camera_id or kwargs.get("camera_id", ""))
        elif isinstance(polygon, list):
            self.camera_id = str(name_or_camera)
            self.name = str(polygon_or_name or zone_id)
            self.polygon = [Point.from_dict(p) for p in polygon]
        else:
            self.name = str(name_or_camera or zone_id)
            self.polygon = []
            self.camera_id = str(camera_id or kwargs.get("camera_id", ""))

        self.applicable_classes = list(applicable_classes if applicable_classes is not None else ["person"])
        self.enabled = bool(enabled)
        self.metadata = dict(metadata or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "camera_id": self.camera_id,
            "name": self.name,
            "polygon": [p.to_dict() for p in self.polygon],
            "applicable_classes": list(self.applicable_classes),
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolygonZone:
        pts = [Point.from_dict(p) for p in data.get("polygon", [])]
        return cls(
            zone_id=str(data["zone_id"]),
            name_or_camera=str(data.get("name", data["zone_id"])),
            polygon_or_name=pts,
            camera_id=str(data.get("camera_id", "")),
            applicable_classes=list(data.get("applicable_classes", ["person"])),
            enabled=bool(data.get("enabled", True)),
            metadata=dict(data.get("metadata", {})),
        )


class VirtualLine:
    def __init__(
        self,
        line_id: str,
        name_or_camera: str = "",
        pa_or_name: Any = None,
        pb_or_pa: Any = None,
        pb: Any = None,
        direction: Any = CrossingDirection.BIDIRECTIONAL,
        applicable_classes: list[str] | None = None,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        camera_id: str | None = None,
        p1: Any = None,
        p2: Any = None,
        point_a: Any = None,
        point_b: Any = None,
        in_direction: Any = None,
        **kwargs: Any,
    ) -> None:
        self.line_id = str(line_id)
        if camera_id is not None:
            self.camera_id = str(camera_id)
        elif pb is not None:
            self.camera_id = str(name_or_camera)
        else:
            self.camera_id = str(kwargs.get("cam_id", ""))

        if name is not None:
            self.name = str(name)
        elif pb is not None:
            self.name = str(pa_or_name or line_id)
        elif isinstance(name_or_camera, str) and name_or_camera:
            self.name = name_or_camera
        else:
            self.name = str(line_id)

        pt_a = point_a if point_a is not None else (p1 if p1 is not None else None)
        pt_b = point_b if point_b is not None else (p2 if p2 is not None else None)

        if pt_a is not None and pt_b is not None:
            self.point_a = Point.from_dict(pt_a)
            self.point_b = Point.from_dict(pt_b)
        elif pb is not None:
            self.point_a = Point.from_dict(pb_or_pa)
            self.point_b = Point.from_dict(pb)
        elif pb_or_pa is not None:
            self.point_a = Point.from_dict(pa_or_name)
            self.point_b = Point.from_dict(pb_or_pa)
        else:
            self.point_a = Point(0.0, 0.0)
            self.point_b = Point(1.0, 1.0)

        raw_in_dir = in_direction if in_direction is not None else kwargs.get("in_direction", "RIGHT_OF_LINE")
        self.in_direction = str(raw_in_dir).upper()

        dir_val = kwargs.get("direction", direction)
        if isinstance(dir_val, CrossingDirection):
            self.direction = dir_val
        elif str(dir_val).upper() == "OUT":
            self.direction = CrossingDirection.OUT
        elif str(dir_val).upper() == "IN":
            self.direction = CrossingDirection.IN
        else:
            self.direction = CrossingDirection.BIDIRECTIONAL

        self.applicable_classes = list(applicable_classes if applicable_classes is not None else ["person"])
        self.enabled = bool(enabled)
        self.metadata = dict(metadata or {})
        self.metadata.update(kwargs)

    @property
    def p1(self) -> Point:
        return self.point_a

    @property
    def p2(self) -> Point:
        return self.point_b

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "camera_id": self.camera_id,
            "name": self.name,
            "point_a": self.point_a.to_dict(),
            "point_b": self.point_b.to_dict(),
            "direction": str(self.direction),
            "applicable_classes": list(self.applicable_classes),
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VirtualLine:
        pa_raw = data.get("point_a") or data.get("p1")
        pb_raw = data.get("point_b") or data.get("p2")
        if pa_raw is None or pb_raw is None:
            raise ValueError("VirtualLine requires point_a (or p1) and point_b (or p2)")
        return cls(
            line_id=str(data["line_id"]),
            name_or_camera=str(data.get("name", data["line_id"])),
            pa_or_name=Point.from_dict(pa_raw),
            pb_or_pa=Point.from_dict(pb_raw),
            camera_id=str(data.get("camera_id", "")),
            direction=data.get("direction", data.get("in_direction", "IN")),
            applicable_classes=list(data.get("applicable_classes", ["person"])),
            enabled=bool(data.get("enabled", True)),
            metadata=dict(data.get("metadata", {})),
        )


class SpatialRule:
    def __init__(
        self,
        rule_id: str,
        name_or_camera: str = "",
        rule_type_or_name: Any = None,
        target_geometry_id: str = "",
        target_id: str = "",
        camera_id: str = "",
        rule_type: Any = None,
        object_classes: list[str] | None = None,
        conditions: dict[str, Any] | None = None,
        threshold: float = 0.0,
        dwell_threshold_seconds: float = 0.0,
        occupancy_threshold: int = 0,
        cooldown_seconds: float = 5.0,
        severity: Any = Severity.WARNING,
        enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        self.rule_id = str(rule_id)
        if isinstance(rule_type_or_name, (RuleType, str)):
            self.name = str(name_or_camera or rule_id)
            self.camera_id = str(camera_id or kwargs.get("cam_id", ""))
            rtype = rule_type_or_name
        elif rule_type is not None:
            self.camera_id = str(name_or_camera)
            self.name = str(rule_type_or_name or rule_id)
            rtype = rule_type
        else:
            self.name = str(name_or_camera or rule_id)
            self.camera_id = str(camera_id)
            rtype = RuleType.ZONE_ENTER

        self.rule_type = RuleType(rtype)
        tgt = target_id or target_geometry_id or kwargs.get("target", "")
        self.target_geometry_id = str(tgt)
        self.object_classes = list(object_classes if object_classes is not None else ["person"])
        self.conditions = dict(conditions or {})
        self.threshold = float(threshold or dwell_threshold_seconds or occupancy_threshold)
        self.cooldown_seconds = float(cooldown_seconds)
        self.severity = Severity(str(severity).upper())
        self.enabled = bool(enabled)

    @property
    def target_id(self) -> str:
        return self.target_geometry_id

    def validate(self) -> tuple[bool, str]:
        if not self.rule_id:
            return False, "rule_id cannot be empty"
        if not self.target_geometry_id:
            return False, "target_geometry_id cannot be empty"
        return True, "Valid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "camera_id": self.camera_id,
            "name": self.name,
            "rule_type": str(self.rule_type),
            "target_geometry_id": self.target_geometry_id,
            "target_id": self.target_geometry_id,
            "object_classes": list(self.object_classes),
            "conditions": dict(self.conditions),
            "threshold": self.threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "severity": str(self.severity),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpatialRule:
        return cls(
            rule_id=str(data["rule_id"]),
            camera_id=str(data.get("camera_id", "")),
            name_or_camera=str(data.get("name", data["rule_id"])),
            rule_type=data["rule_type"],
            target_id=str(data.get("target_id", data.get("target_geometry_id", data.get("zone_id", data.get("line_id", ""))))),
            object_classes=list(data.get("object_classes", data.get("classes", ["person"]))),
            conditions=dict(data.get("conditions", {})),
            threshold=float(data.get("threshold", data.get("dwell_threshold_seconds", data.get("occupancy_threshold", 0.0)))),
            cooldown_seconds=float(data.get("cooldown_seconds", 5.0)),
            severity=data.get("severity", "WARNING"),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass
class EvidenceReference:
    evidence_id: str
    event_id: str
    camera_id: str
    track_id: str
    capture_timestamp_utc: str
    bbox: list[float]
    image_path: str | None = None
    quality_score: float = 0.0
    source_dimensions: tuple[int, int] = (1280, 720)
    crop_filename: str = ""

    def __post_init__(self) -> None:
        if not self.crop_filename and self.image_path:
            import os
            self.crop_filename = os.path.basename(self.image_path)
        elif not self.crop_filename:
            self.crop_filename = f"{self.camera_id}_track{self.track_id}_{self.evidence_id}.jpg"

    @property
    def crop_jpeg_url(self) -> str:
        return f"/api/evidence/{self.crop_filename}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "track_id": self.track_id,
            "capture_timestamp_utc": self.capture_timestamp_utc,
            "bbox": [round(b, 2) for b in self.bbox],
            "image_path": self.image_path,
            "crop_filename": self.crop_filename,
            "crop_jpeg_url": self.crop_jpeg_url,
            "quality_score": round(self.quality_score, 4),
            "source_dimensions": list(self.source_dimensions),
        }


@dataclass
class SpatialEvent:
    event_id: str
    event_type: str
    event_status: EventStatus
    camera_id: str
    track_id: str
    track_session_id: str
    rule_id: str
    geometry_id: str
    object_class: str
    event_time_utc: str
    started_at_utc: str
    ended_at_utc: str | None = None
    confidence: float = 1.0
    config_version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence_reference: EvidenceReference | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_status": str(self.event_status),
            "camera_id": self.camera_id,
            "track_id": self.track_id,
            "track_session_id": self.track_session_id,
            "rule_id": self.rule_id,
            "geometry_id": self.geometry_id,
            "object_class": self.object_class,
            "event_time_utc": self.event_time_utc,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "confidence": round(self.confidence, 4),
            "config_version": self.config_version,
            "metadata": self.metadata,
            "evidence": self.evidence_reference.to_dict() if self.evidence_reference else None,
        }

    @property
    def status(self) -> EventStatus:
        return self.event_status

    @status.setter
    def status(self, val: EventStatus) -> None:
        self.event_status = val

    @property
    def dwell_duration_ms(self) -> float:
        return float(self.metadata.get("dwell_ms", self.metadata.get("dwell_duration_ms", 0.0)))


@dataclass
class OccupancyState:
    camera_id: str
    visible_occupancy: int = 0
    flow_occupancy: int = 0
    baseline: int = 0
    total_in: int = 0
    total_out: int = 0
    is_uncertain: bool = False
    last_reconciled_utc: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "visible_occupancy": max(0, self.visible_occupancy),
            "flow_occupancy": max(0, self.flow_occupancy),
            "baseline": self.baseline,
            "total_in": self.total_in,
            "total_out": self.total_out,
            "is_uncertain": self.is_uncertain,
            "last_reconciled_utc": self.last_reconciled_utc,
        }


class TrackInput:
    def __init__(
        self,
        camera_id: str,
        track_id: Any,
        *args: Any,
        class_id: int = 0,
        class_name: str = "person",
        bbox_xyxy: tuple[float, float, float, float] | list[float] = (0.0, 0.0, 0.0, 0.0),
        confidence: float = 1.0,
        track_state: str = "CONFIRMED",
        timestamp_ns: int = 0,
        frame_sequence: int = 0,
        frame_width: int = 1280,
        frame_height: int = 720,
        trajectory: list[tuple[float, float]] | None = None,
        track_session_id: str = "default",
        **kwargs: Any,
    ) -> None:
        self.camera_id = str(camera_id)
        self.track_id = str(track_id)

        # Handle positional args unpack
        if len(args) >= 7 and isinstance(args[0], (int, float)):
            self.class_id = int(args[0])
            self.class_name = str(args[1])
            self.bbox_xyxy = tuple(args[2])
            self.confidence = float(args[3])
            self.track_state = str(args[4])
            self.timestamp_ns = int(args[5])
            self.frame_sequence = int(args[6])
            self.frame_width = int(args[7]) if len(args) > 7 else 1280
            self.frame_height = int(args[8]) if len(args) > 8 else 720
        elif len(args) >= 5 and isinstance(args[0], str):
            self.class_id = class_id
            self.class_name = str(args[0])
            self.bbox_xyxy = tuple(args[1])
            self.confidence = float(args[2])
            self.frame_sequence = int(args[3])
            self.timestamp_ns = int(args[4])
            self.frame_width = int(args[5]) if len(args) > 5 else 1280
            self.frame_height = int(args[6]) if len(args) > 6 else 720
            self.track_state = track_state
        else:
            self.class_id = int(class_id)
            self.class_name = str(kwargs.get("class_name", class_name))
            self.bbox_xyxy = tuple(kwargs.get("bbox_xyxy", bbox_xyxy))
            self.confidence = float(kwargs.get("confidence", confidence))
            self.track_state = str(kwargs.get("track_state", track_state))
            self.timestamp_ns = int(kwargs.get("timestamp_ns", timestamp_ns))
            self.frame_sequence = int(kwargs.get("frame_sequence", frame_sequence))
            self.frame_width = int(kwargs.get("frame_width", frame_width))
            self.frame_height = int(kwargs.get("frame_height", frame_height))

        self.trajectory = list(trajectory or kwargs.get("trajectory", []))
        self.track_session_id = str(track_session_id or kwargs.get("track_session_id", "default"))
