from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any

from .types import Point

logger = logging.getLogger("intelligence.dwell")


@dataclass
class DwellEvent:
    event_type: str  # "DWELL_THRESHOLD"
    camera_id: str
    track_id: str
    track_session_id: str
    zone_id: str
    object_class: str
    dwell_duration_ms: float
    threshold_seconds: float
    timestamp_ns: int
    anchor_point: Point
    is_uncertain: bool = False


@dataclass
class TrackDwellRecord:
    camera_id: str
    track_id: str
    zone_id: str
    object_class: str
    entered_at_monotonic_ns: int
    last_confirmed_inside_ns: int
    accumulated_dwell_ms: float = 0.0
    threshold_emitted: set[float] = field(default_factory=set)  # set of threshold_seconds already emitted
    visibility_state: str = "VISIBLE"  # "VISIBLE", "LOST", "EXITED"
    last_anchor: Point = field(default_factory=lambda: Point(0.0, 0.0))
    is_uncertain: bool = False


class DwellManager:
    """Tracks dwell duration of objects inside zones with occlusion grace handling."""

    def __init__(self, config: Any = None, *, occlusion_grace_ms: float = 2000.0) -> None:
        if config is not None and hasattr(config, "dwell_occlusion_grace_ms"):
            self.occlusion_grace_ms = config.dwell_occlusion_grace_ms
        elif isinstance(config, (int, float)):
            self.occlusion_grace_ms = float(config)
        else:
            self.occlusion_grace_ms = occlusion_grace_ms
        # (camera_id, track_id, zone_id) -> TrackDwellRecord
        self._records: dict[tuple[str, str, str], TrackDwellRecord] = {}

    def on_zone_enter(
        self,
        camera_id: str,
        track_id: str,
        track_session_id: str,
        zone_id: str,
        object_class: str,
        timestamp_ns: int,
        anchor_point: Point,
    ) -> None:
        now_mono = time.monotonic_ns()
        key = (camera_id, track_id, zone_id)
        self._records[key] = TrackDwellRecord(
            camera_id=camera_id,
            track_id=track_id,
            zone_id=zone_id,
            object_class=object_class,
            entered_at_monotonic_ns=now_mono,
            last_confirmed_inside_ns=now_mono,
            accumulated_dwell_ms=0.0,
            threshold_emitted=set(),
            visibility_state="VISIBLE",
            last_anchor=anchor_point,
            is_uncertain=False,
        )

    def update_track_in_zone(self, camera_id: str, track_id: Any, zone_id: str, timestamp_ns: int) -> float:
        tid = str(track_id)
        key = (camera_id, tid, zone_id)
        rec = self._records.get(key)
        if rec is None:
            self._records[key] = TrackDwellRecord(
                camera_id=camera_id,
                track_id=tid,
                zone_id=zone_id,
                object_class="person",
                entered_at_monotonic_ns=timestamp_ns,
                last_confirmed_inside_ns=timestamp_ns,
                accumulated_dwell_ms=0.0,
                threshold_emitted=set(),
                visibility_state="VISIBLE",
                last_anchor=Point(0.0, 0.0),
                is_uncertain=False,
            )
            return 0.0
        else:
            elapsed_ms = (timestamp_ns - rec.last_confirmed_inside_ns) / 1_000_000.0
            rec.accumulated_dwell_ms += max(0.0, elapsed_ms)
            rec.last_confirmed_inside_ns = timestamp_ns
            return rec.accumulated_dwell_ms

    def mark_track_active(self, camera_id: str, track_id: Any, timestamp_ns: int) -> None:
        pass

    def check_dwell_thresholds(self, camera_id: str, track_id: Any, zone_id: str, timestamp_ns: int, thresholds: list[float]) -> list[dict[str, Any]]:
        tid = str(track_id)
        key = (camera_id, tid, zone_id)
        rec = self._records.get(key)
        if not rec:
            return []
        dwell_sec = rec.accumulated_dwell_ms / 1000.0
        results = []
        for th in thresholds:
            if dwell_sec >= th and th not in rec.threshold_emitted:
                rec.threshold_emitted.add(th)
                results.append({"threshold_seconds": th, "dwell_seconds": dwell_sec})
        return results

    def check_occlusions(self, camera_id: str, timestamp_ns: int) -> None:
        to_del = []
        for key, rec in self._records.items():
            if rec.camera_id == camera_id:
                if (timestamp_ns - rec.last_confirmed_inside_ns) / 1_000_000.0 > self.occlusion_grace_ms:
                    to_del.append(key)
        for k in to_del:
            del self._records[k]

    def get_dwell_ms(self, camera_id: str, track_id: Any, zone_id: str) -> float:
        tid = str(track_id)
        key = (camera_id, tid, zone_id)
        rec = self._records.get(key)
        return rec.accumulated_dwell_ms if rec else 0.0

    def update_presence(
        self,
        camera_id: str,
        track_id: str,
        zone_id: str,
        anchor_point: Point,
        track_state: str = "CONFIRMED",
    ) -> None:
        key = (camera_id, track_id, zone_id)
        rec = self._records.get(key)
        if rec is None or rec.visibility_state == "EXITED":
            return

        now_mono = time.monotonic_ns()
        rec.last_anchor = anchor_point

        if track_state in ("CONFIRMED", "TENTATIVE"):
            if rec.visibility_state == "LOST":
                # Recovered from occlusion
                rec.visibility_state = "VISIBLE"
                rec.last_confirmed_inside_ns = now_mono
            else:
                elapsed_ms = (now_mono - rec.last_confirmed_inside_ns) / 1_000_000.0
                rec.accumulated_dwell_ms += max(0.0, elapsed_ms)
                rec.last_confirmed_inside_ns = now_mono

        elif track_state == "LOST":
            time_since_seen_ms = (now_mono - rec.last_confirmed_inside_ns) / 1_000_000.0
            if time_since_seen_ms > self.occlusion_grace_ms:
                rec.visibility_state = "LOST"
                rec.is_uncertain = True
                # Do not accumulate dwell while unconfirmed past grace period

    def check_thresholds(
        self,
        camera_id: str,
        track_id: str,
        track_session_id: str,
        zone_id: str,
        threshold_seconds: float,
        timestamp_ns: int,
    ) -> list[DwellEvent]:
        """Check if dwell duration has crossed threshold and emit event ONCE per threshold."""
        events: list[DwellEvent] = []
        key = (camera_id, track_id, zone_id)
        rec = self._records.get(key)
        if rec is None or rec.visibility_state == "EXITED":
            return events

        # Also update accumulated dwell up to now if visible
        now_mono = time.monotonic_ns()
        if rec.visibility_state == "VISIBLE":
            elapsed_ms = (now_mono - rec.last_confirmed_inside_ns) / 1_000_000.0
            rec.accumulated_dwell_ms += max(0.0, elapsed_ms)
            rec.last_confirmed_inside_ns = now_mono

        thresh_ms = threshold_seconds * 1000.0
        if rec.accumulated_dwell_ms >= thresh_ms and threshold_seconds not in rec.threshold_emitted:
            rec.threshold_emitted.add(threshold_seconds)
            events.append(
                DwellEvent(
                    event_type="DWELL_THRESHOLD",
                    camera_id=camera_id,
                    track_id=track_id,
                    track_session_id=track_session_id,
                    zone_id=zone_id,
                    object_class=rec.object_class,
                    dwell_duration_ms=rec.accumulated_dwell_ms,
                    threshold_seconds=threshold_seconds,
                    timestamp_ns=timestamp_ns,
                    anchor_point=rec.last_anchor,
                    is_uncertain=rec.is_uncertain,
                )
            )

        return events

    def on_zone_exit(
        self,
        camera_id: str,
        track_id: str,
        zone_id: str,
    ) -> float:
        """Returns final accumulated dwell duration in milliseconds."""
        key = (camera_id, track_id, zone_id)
        rec = self._records.pop(key, None)
        if rec:
            rec.visibility_state = "EXITED"
            return max(0.0, rec.accumulated_dwell_ms)
        return 0.0

    def get_dwell_ms(self, camera_id: str, track_id: str, zone_id: str) -> float:
        key = (camera_id, track_id, zone_id)
        rec = self._records.get(key)
        if rec:
            return max(0.0, rec.accumulated_dwell_ms)
        return 0.0

    def prune_track(self, camera_id: str, track_id: str) -> None:
        for k in list(self._records.keys()):
            if k[0] == camera_id and k[1] == track_id:
                self._records.pop(k, None)

    def reset_camera(self, camera_id: str) -> None:
        for k in list(self._records.keys()):
            if k[0] == camera_id:
                self._records.pop(k, None)
