from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any

from .geometry import bounding_box_anchor, point_in_polygon
from .types import AnchorType, Point, PolygonZone, ZoneState

logger = logging.getLogger("intelligence.zone")


@dataclass
class ZoneTransitionEvent:
    event_type: str  # "ZONE_ENTER" or "ZONE_EXIT"
    camera_id: str
    track_id: str
    track_session_id: str
    zone_id: str
    object_class: str
    timestamp_ns: int
    anchor_point: Point
    dwell_duration_ms: float = 0.0


class ActiveTrackList(list):
    def __contains__(self, item: Any) -> bool:
        if super().__contains__(item):
            return True
        if str(item) in [str(x) for x in self]:
            return True
        try:
            item_int = int(item)
            if any(str(x).isdigit() and int(x) == item_int for x in self):
                return True
        except (ValueError, TypeError):
            pass
        return False


@dataclass
class TrackZoneState:
    zone_id: str
    state: ZoneState = ZoneState.OUTSIDE
    inside_count: int = 0
    outside_count: int = 0
    entered_monotonic_ns: int = 0
    last_seen_monotonic_ns: int = 0
    last_anchor: Point = field(default_factory=lambda: Point(0.0, 0.0))


class ZoneManager:
    """Evaluates spatial zone transitions (ENTER / EXIT) with boundary hysteresis."""

    def __init__(
        self,
        config: Any = None,
        *,
        entry_confirmations: int = 2,
        exit_confirmations: int = 2,
        boundary_margin_ratio: float = 0.01,
        anchor_type: AnchorType = AnchorType.BOTTOM_CENTER,
    ) -> None:
        if config is not None and hasattr(config, "entry_confirmation_updates"):
            self.entry_confirmations = config.entry_confirmation_updates
            self.exit_confirmations = config.exit_confirmation_updates
            self.boundary_margin_ratio = config.boundary_margin_ratio
            self.anchor_type = config.anchor_type
        else:
            self.entry_confirmations = max(1, entry_confirmations)
            self.exit_confirmations = max(1, exit_confirmations)
            self.boundary_margin_ratio = boundary_margin_ratio
            self.anchor_type = anchor_type

        # (camera_id, zone_id) -> PolygonZone
        self._zones: dict[tuple[str, str], PolygonZone] = {}
        # (camera_id, track_id, zone_id) -> TrackZoneState
        self._states: dict[tuple[str, str, str], TrackZoneState] = {}
        # (camera_id, track_id) -> set of zone_ids currently inside
        self._active_inside: dict[tuple[str, str], set[str]] = {}

    def set_zones(self, camera_id: str, zones: list[PolygonZone]) -> None:
        """Register or replace zones for a camera, reconciling state on geometry changes."""
        old_zone_ids = {zid for (cid, zid) in self._zones if cid == camera_id}
        new_zone_ids = {z.zone_id for z in zones}

        # Remove deleted zones
        deleted = old_zone_ids - new_zone_ids
        for zid in deleted:
            self._zones.pop((camera_id, zid), None)
            # Clean up track states
            for k in list(self._states.keys()):
                if k[0] == camera_id and k[2] == zid:
                    self._states.pop(k, None)
            for k, active_set in list(self._active_inside.items()):
                if k[0] == camera_id:
                    active_set.discard(zid)

        # Store new zones
        for z in zones:
            self._zones[(camera_id, z.zone_id)] = z

    def get_zones(self, camera_id: str) -> list[PolygonZone]:
        return [z for (cid, _), z in self._zones.items() if cid == camera_id]

    def get_zone(self, camera_id: str, zone_id: str) -> PolygonZone | None:
        return self._zones.get((camera_id, zone_id))

    def reset_camera(self, camera_id: str) -> None:
        """Reset all track states for camera (e.g. on disconnect/reconnect)."""
        for k in list(self._states.keys()):
            if k[0] == camera_id:
                self._states.pop(k, None)
        for k in list(self._active_inside.keys()):
            if k[0] == camera_id:
                self._active_inside.pop(k, None)

    def prune_track(self, camera_id: str, track_id: str) -> list[ZoneTransitionEvent]:
        """Track ended or removed: emit ZONE_EXIT for any zone currently marked inside."""
        events: list[ZoneTransitionEvent] = []
        now_mono = time.monotonic_ns()
        track_key = (camera_id, track_id)

        inside_zones = list(self._active_inside.get(track_key, set()))
        for zone_id in inside_zones:
            state_key = (camera_id, track_id, zone_id)
            st = self._states.pop(state_key, None)
            if st and st.state in (ZoneState.INSIDE, ZoneState.PENDING_EXIT):
                dwell_ms = (now_mono - st.entered_monotonic_ns) / 1_000_000.0 if st.entered_monotonic_ns > 0 else 0.0
                events.append(
                    ZoneTransitionEvent(
                        event_type="ZONE_EXIT",
                        camera_id=camera_id,
                        track_id=track_id,
                        track_session_id="default",
                        zone_id=zone_id,
                        object_class="unknown",
                        timestamp_ns=now_mono,
                        anchor_point=st.last_anchor,
                        dwell_duration_ms=max(0.0, dwell_ms),
                    )
                )

        self._active_inside.pop(track_key, None)
        return events

    def update_track(
        self,
        camera_id: str,
        track_id: Any,
        class_name: str = "person",
        bbox_xyxy: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
        source_width: int = 1280,
        source_height: int = 720,
        timestamp_ns: int = 0,
        track_session_id: str = "default",
        track_state: str = "CONFIRMED",
    ) -> list[ZoneTransitionEvent]:
        """Update track position and evaluate zone enter/exit transitions."""
        if hasattr(track_id, "bbox_xyxy"):
            t = track_id
            track_id = str(getattr(t, "global_track_id", getattr(t, "track_id", "0")))
            class_name = getattr(t, "class_name", class_name)
            bbox_xyxy = getattr(t, "bbox_xyxy", bbox_xyxy)
            source_width = getattr(t, "frame_width", getattr(t, "source_width", source_width))
            source_height = getattr(t, "frame_height", getattr(t, "source_height", source_height))
            timestamp_ns = getattr(t, "timestamp_ns", timestamp_ns)
            track_session_id = getattr(t, "track_session_id", track_session_id)
            track_state = getattr(t, "track_state", getattr(t, "state", track_state))
        else:
            track_id = str(track_id)

        events: list[ZoneTransitionEvent] = []
        now_mono = time.monotonic_ns()

        # Compute normalized anchor point
        anchor = bounding_box_anchor(
            bbox_xyxy,
            anchor_type=self.anchor_type,
            width=source_width,
            height=source_height,
        )

        relevant_zones = [
            z for (cid, _), z in self._zones.items()
            if cid == camera_id and z.enabled and (not z.applicable_classes or class_name.lower() in [c.lower() for c in z.applicable_classes])
        ]

        track_key = (camera_id, track_id)

        for zone in relevant_zones:
            state_key = (camera_id, track_id, zone.zone_id)
            st = self._states.get(state_key)
            if st is None:
                st = TrackZoneState(zone_id=zone.zone_id)
                self._states[state_key] = st

            st.last_anchor = anchor
            st.last_seen_monotonic_ns = now_mono

            # Test point in polygon with boundary margin hysteresis
            # When currently INSIDE: require escaping past boundary margin to exit (relaxed margin)
            # When currently OUTSIDE: require entering past boundary margin to enter (strict margin)
            margin = self.boundary_margin_ratio if st.state == ZoneState.OUTSIDE else -self.boundary_margin_ratio
            is_inside_poly = point_in_polygon(anchor, zone.polygon, margin=margin)

            if is_inside_poly:
                st.inside_count += 1
                st.outside_count = 0

                if st.state == ZoneState.OUTSIDE:
                    st.state = ZoneState.PENDING_ENTER

                if st.state == ZoneState.PENDING_ENTER and st.inside_count >= self.entry_confirmations:
                    st.state = ZoneState.INSIDE
                    st.entered_monotonic_ns = now_mono
                    self._active_inside.setdefault(track_key, set()).add(zone.zone_id)

                    events.append(
                        ZoneTransitionEvent(
                            event_type="ZONE_ENTER",
                            camera_id=camera_id,
                            track_id=track_id,
                            track_session_id=track_session_id,
                            zone_id=zone.zone_id,
                            object_class=class_name,
                            timestamp_ns=timestamp_ns,
                            anchor_point=anchor,
                            dwell_duration_ms=0.0,
                        )
                    )

                elif st.state == ZoneState.PENDING_EXIT:
                    # Regained stable inside state; cancel pending exit
                    st.state = ZoneState.INSIDE

            else:
                st.outside_count += 1
                st.inside_count = 0

                if st.state == ZoneState.INSIDE:
                    st.state = ZoneState.PENDING_EXIT

                if st.state in (ZoneState.PENDING_EXIT, ZoneState.PENDING_ENTER) and st.outside_count >= self.exit_confirmations:
                    prior_state = st.state
                    st.state = ZoneState.OUTSIDE
                    self._active_inside.setdefault(track_key, set()).discard(zone.zone_id)

                    if prior_state == ZoneState.PENDING_EXIT:
                        dwell_ms = (now_mono - st.entered_monotonic_ns) / 1_000_000.0 if st.entered_monotonic_ns > 0 else 0.0
                        events.append(
                            ZoneTransitionEvent(
                                event_type="ZONE_EXIT",
                                camera_id=camera_id,
                                track_id=track_id,
                                track_session_id=track_session_id,
                                zone_id=zone.zone_id,
                                object_class=class_name,
                                timestamp_ns=timestamp_ns,
                                anchor_point=anchor,
                                dwell_duration_ms=max(0.0, dwell_ms),
                            )
                        )

        return events

    def get_tracks_inside_zone(self, camera_id: str, zone_id: str) -> list[str]:
        """Return all track IDs currently confirmed INSIDE this zone."""
        tracks = ActiveTrackList()
        for (cid, tid, zid), st in self._states.items():
            if cid == camera_id and zid == zone_id and st.state in (ZoneState.INSIDE, ZoneState.PENDING_EXIT):
                tracks.append(tid)
        return tracks

    def get_active_tracks_in_zone(self, camera_id: str, zone_id: str) -> list[Any]:
        return self.get_tracks_inside_zone(camera_id, zone_id)
