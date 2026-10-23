from __future__ import annotations

from dataclasses import dataclass
from .types import AnchorType


@dataclass(frozen=True, slots=True)
class SpatialConfig:
    anchor_type: AnchorType = AnchorType.BOTTOM_CENTER
    entry_confirmation_updates: int = 2
    exit_confirmation_updates: int = 2
    boundary_margin_ratio: float = 0.01

    # Virtual Line parameters
    line_crossing_min_movement: float = 0.008
    line_crossing_cooldown_seconds: float = 2.0
    line_rearm_distance_ratio: float = 0.03
    max_trajectory_gap_ratio: float = 0.6

    # Dwell parameters
    dwell_occlusion_grace_ms: float = 2000.0

    # Storage & cache boundedness
    max_active_events: int = 1000
    max_recent_events: int = 5000
    event_storage_path: str = "config/streamcore/events.jsonl"
    spatial_rules_path: str = "config/streamcore/spatial_rules.json"
    evidence_storage_dir: str = "runtime/streamcore/output/evidence"
