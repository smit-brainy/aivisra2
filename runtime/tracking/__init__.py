"""AIVISRA Stage 5: Multi-Camera Tracking + Track Lifecycle + Best Crop Subsystem."""

from .types import (
    Direction,
    TrackState,
    Track,
    TrajectoryPoint,
    BestCropMetadata,
    TrackingConfig,
)
from .tracker_adapter import BaseTracker
from .bytetrack_adapter import ByteTrackAdapter
from .tracker_manager import TrackerManager
from .track_store import TrackStore
from .track_lifecycle import TrackLifecycle
from .best_crop import BestCropSelector
from .metrics import TrackingMetrics
from .track_exporter import TracksJsonWriter

__all__ = [
    "Direction",
    "TrackState",
    "Track",
    "TrajectoryPoint",
    "BestCropMetadata",
    "TrackingConfig",
    "BaseTracker",
    "ByteTrackAdapter",
    "TrackerManager",
    "TrackStore",
    "TrackLifecycle",
    "BestCropSelector",
    "TrackingMetrics",
    "TracksJsonWriter",
]

