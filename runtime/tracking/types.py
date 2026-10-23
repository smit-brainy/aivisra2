from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TrackState(StrEnum):
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"
    LOST = "LOST"
    ENDED = "ENDED"


class Direction(StrEnum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    UP = "UP"
    DOWN = "DOWN"
    STATIONARY = "STATIONARY"


@dataclass(slots=True)
class TrajectoryPoint:
    cx: float
    cy: float
    timestamp_ns: int


@dataclass(slots=True)
class BestCropMetadata:
    track_id: str
    camera_id: str
    frame_sequence: int
    timestamp_ns: int
    bbox_xyxy: tuple[float, float, float, float]
    quality_score: float
    image_bytes: bytes | None = None
    width: int = 0
    height: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "frame_sequence": self.frame_sequence,
            "timestamp_ns": self.timestamp_ns,
            "bbox_xyxy": list(self.bbox_xyxy),
            "quality_score": round(self.quality_score, 4),
            "has_image": self.image_bytes is not None,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class Track:
    camera_id: str
    local_track_id: int
    global_track_id: str
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    first_seen_ns: int
    last_seen_ns: int
    duration_ms: float = 0.0
    state: TrackState = TrackState.TENTATIVE
    hit_count: int = 1
    miss_count: int = 0
    trajectory: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=128))
    trajectory_timestamps: deque[int] = field(default_factory=lambda: deque(maxlen=128))
    velocity: tuple[float, float] = (0.0, 0.0)
    direction: Direction = Direction.STATIONARY
    best_crop_score: float = 0.0
    best_crop_metadata: BestCropMetadata | None = None

    def to_dict(self, include_trajectory: bool = True) -> dict[str, Any]:
        d = {
            "camera_id": self.camera_id,
            "local_track_id": self.local_track_id,
            "track_id": self.global_track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 4),
            "bbox_xyxy": [round(v, 1) for v in self.bbox_xyxy],
            "first_seen_ns": self.first_seen_ns,
            "last_seen_ns": self.last_seen_ns,
            "duration_ms": round(self.duration_ms, 1),
            "state": str(self.state),
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "velocity": [round(self.velocity[0], 2), round(self.velocity[1], 2)],
            "direction": str(self.direction),
            "best_crop_score": round(self.best_crop_score, 3),
            "best_crop": self.best_crop_metadata.to_dict() if self.best_crop_metadata else None,
        }
        if include_trajectory:
            d["trajectory"] = [[round(p[0], 1), round(p[1], 1)] for p in self.trajectory]
        return d


@dataclass(frozen=True, slots=True)
class TrackingConfig:
    enabled: bool = True
    tracker: str = "bytetrack"
    class_aware: bool = True
    min_hits_to_confirm: int = 3
    lost_timeout_ms: float = 1000.0
    end_timeout_ms: float = 3000.0
    track_high_thresh: float = 0.5
    track_low_thresh: float = 0.1
    match_thresh: float = 0.8
    max_trajectory_points: int = 128
    minimum_crop_improvement: float = 0.05
    stationary_threshold_px_s: float = 8.0
    export_json: bool = False
    output_path: str = ""

