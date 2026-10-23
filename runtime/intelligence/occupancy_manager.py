from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any

from .types import OccupancyState

logger = logging.getLogger("intelligence.occupancy")


@dataclass
class FlowOccupancyRecord:
    camera_id: str
    baseline: int = 0
    total_in: int = 0
    total_out: int = 0
    raw_occupancy: int = 0
    displayed_occupancy: int = 0
    is_uncertain: bool = False
    last_reconciled_utc: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )


class OccupancyManager:
    """Manages Visible Zone Occupancy and Flow-Based Occupancy as two distinct metrics."""

    def __init__(self, config: Any = None) -> None:
        self.config = config
        # camera_id -> FlowOccupancyRecord
        self._flow_records: dict[str, FlowOccupancyRecord] = {}
        # (camera_id, zone_id) -> set of track_ids currently inside
        self._visible_zone_tracks: dict[tuple[str, str], set[str]] = {}

    def configure_camera(self, camera_id: str, baseline: int = 0) -> None:
        rec = self._flow_records.setdefault(
            camera_id,
            FlowOccupancyRecord(camera_id=camera_id, baseline=baseline),
        )
        rec.baseline = baseline
        self._recalculate(camera_id)

    set_baseline = configure_camera

    def on_line_crossing(self, camera_id: str, direction: str, count: int = 1) -> None:
        """Update flow occupancy from verified IN / OUT line crossing events."""
        rec = self._flow_records.setdefault(camera_id, FlowOccupancyRecord(camera_id=camera_id))
        if direction == "IN":
            rec.total_in += count
        elif direction == "OUT":
            rec.total_out += count
        self._recalculate(camera_id)

    record_crossing = on_line_crossing

    def on_zone_presence_update(self, camera_id: str, zone_id: str, track_ids: list[str]) -> None:
        """Update visible zone occupancy directly from active confirmed tracks in zone."""
        key = (camera_id, zone_id)
        self._visible_zone_tracks[key] = set(track_ids)

    def update_visible_occupancy(self, camera_id: str, zone_id: str, count_or_tracks: Any) -> None:
        """Update visible headcount from count or list of track IDs."""
        key = (camera_id, zone_id)
        if isinstance(count_or_tracks, int):
            self._visible_zone_tracks[key] = {f"trk_{i}" for i in range(count_or_tracks)}
        else:
            self._visible_zone_tracks[key] = set(count_or_tracks)

    def get_visible_occupancy(self, camera_id: str, zone_id: str | None = None) -> int:
        """Get instantaneous headcount of visible tracks currently in zone(s)."""
        if zone_id is not None:
            return len(self._visible_zone_tracks.get((camera_id, zone_id), set()))
        # Total across all zones for camera
        all_tracks: set[str] = set()
        for (cid, _), trks in self._visible_zone_tracks.items():
            if cid == camera_id:
                all_tracks.update(trks)
        return len(all_tracks)

    def get_flow_occupancy(self, camera_id: str) -> OccupancyState:
        """Get flow-based occupancy state."""
        rec = self._flow_records.setdefault(camera_id, FlowOccupancyRecord(camera_id=camera_id))
        return OccupancyState(
            camera_id=camera_id,
            visible_occupancy=self.get_visible_occupancy(camera_id),
            flow_occupancy=rec.displayed_occupancy,
            baseline=rec.baseline,
            total_in=rec.total_in,
            total_out=rec.total_out,
            is_uncertain=rec.is_uncertain,
            last_reconciled_utc=rec.last_reconciled_utc,
        )

    def reconcile_flow(
        self,
        camera_id: str,
        new_count: int,
        reason: str = "manual_calibration",
    ) -> OccupancyState:
        """Calibrate flow occupancy to a known reference count."""
        rec = self._flow_records.setdefault(camera_id, FlowOccupancyRecord(camera_id=camera_id))
        target = max(0, new_count)
        rec.baseline = target
        rec.total_in = 0
        rec.total_out = 0
        rec.is_uncertain = False
        rec.last_reconciled_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._recalculate(camera_id)
        logger.info(
            "flow_occupancy_reconciled",
            extra={"camera_id": camera_id, "new_count": target, "reason": reason},
        )
        return self.get_flow_occupancy(camera_id)

    reconcile = reconcile_flow

    def mark_uncertain(self, camera_id: str) -> None:
        """Flag occupancy as uncertain (e.g. following camera offline, missed frames, or restart)."""
        rec = self._flow_records.get(camera_id)
        if rec:
            rec.is_uncertain = True

    def reset_camera(self, camera_id: str) -> None:
        """Reset visible tracks on camera disconnect."""
        for k in list(self._visible_zone_tracks.keys()):
            if k[0] == camera_id:
                self._visible_zone_tracks[k] = set()
        self.mark_uncertain(camera_id)

    def _recalculate(self, camera_id: str) -> None:
        rec = self._flow_records.get(camera_id)
        if rec:
            rec.raw_occupancy = rec.baseline + rec.total_in - rec.total_out
            if rec.raw_occupancy < 0:
                rec.is_uncertain = True
            rec.displayed_occupancy = max(0, rec.raw_occupancy)
