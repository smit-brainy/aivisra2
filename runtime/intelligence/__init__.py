from __future__ import annotations

from .config import SpatialConfig
from .dwell_manager import DwellEvent, DwellManager
from .event_manager import EventManager
from .event_store import EventStore, LocalJsonEventStore
from .evidence_manager import EvidenceManager
from .geometry import (
    bounding_box_anchor,
    denormalize_coordinates,
    distance_point_to_segment,
    line_validation,
    normalize_coordinates,
    point_in_polygon,
    polygon_area,
    polygon_validation,
    segment_intersection,
    signed_line_distance,
    signed_line_side,
)
from .line_crossing import LineCrossingEvent, LineCrossingManager
from .metrics import IntelligenceMetrics
from .occupancy_manager import OccupancyManager
from .rule_engine import RuleEngine, TriggeredRuleMatch
from .spatial_manager import SpatialManager
from .types import (
    AnchorType,
    CrossingDirection,
    EventStatus,
    EvidenceReference,
    OccupancyState,
    Point,
    PolygonZone,
    RuleType,
    Severity,
    SpatialEvent,
    SpatialRule,
    TrackInput,
    VirtualLine,
    ZoneState,
)
from .zone_manager import ZoneManager, ZoneTransitionEvent

__all__ = [
    "AnchorType",
    "CrossingDirection",
    "DwellEvent",
    "DwellManager",
    "EventManager",
    "EventStatus",
    "EventStore",
    "EvidenceManager",
    "EvidenceReference",
    "IntelligenceMetrics",
    "LineCrossingEvent",
    "LineCrossingManager",
    "LocalJsonEventStore",
    "OccupancyManager",
    "OccupancyState",
    "Point",
    "PolygonZone",
    "RuleEngine",
    "RuleType",
    "Severity",
    "SpatialConfig",
    "SpatialEvent",
    "SpatialManager",
    "SpatialRule",
    "TrackInput",
    "TriggeredRuleMatch",
    "VirtualLine",
    "ZoneManager",
    "ZoneState",
    "ZoneTransitionEvent",
    "bounding_box_anchor",
    "denormalize_coordinates",
    "distance_point_to_segment",
    "line_validation",
    "normalize_coordinates",
    "point_in_polygon",
    "polygon_area",
    "polygon_validation",
    "segment_intersection",
    "signed_line_distance",
    "signed_line_side",
]

