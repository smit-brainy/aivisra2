from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..streamcore.types import Detection
from .types import Track, TrackingConfig


class BaseTracker(ABC):
    """Abstract base tracker interface per camera."""

    def __init__(self, camera_id: str, config: TrackingConfig) -> None:
        self.camera_id = camera_id
        self.config = config

    @abstractmethod
    def update(
        self,
        detections: list[Detection],
        timestamp_ns: int,
        frame_sequence: int,
        source_width: int,
        source_height: int,
        frame_image: Any = None,
    ) -> list[Track]:
        """Process fresh detections for this camera and return active tracks."""
        pass

    @abstractmethod
    def get_tracks(self) -> list[Track]:
        """Return all current tracks for this camera."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Clear all active tracks and state."""
        pass

