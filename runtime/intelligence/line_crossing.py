from __future__ import annotations

from dataclasses import dataclass, field
import logging
import math
import time
from typing import Any

from .geometry import (
    bounding_box_anchor,
    distance_point_to_segment,
    segment_intersection,
    signed_line_distance,
    signed_line_side,
)
from .types import AnchorType, CrossingDirection, Point, VirtualLine

logger = logging.getLogger("intelligence.line")


@dataclass
class LineCrossingEvent:
    event_type: str = "LINE_CROSSING"
    camera_id: str = ""
    track_id: str = ""
    track_session_id: str = "default"
    line_id: str = ""
    crossing_direction: str = "IN"
    object_class: str = "person"
    timestamp_ns: int = 0
    crossing_point: Point = field(default_factory=lambda: Point(0.0, 0.0))
    direction: str | None = None

    def __post_init__(self) -> None:
        if self.direction is not None:
            self.crossing_direction = self.direction
        else:
            self.direction = self.crossing_direction


@dataclass
class TrackLineState:
    line_id: str
    last_anchor: Point | None = None
    last_side: float = 0.0
    last_crossing_time_mono: float = 0.0
    last_crossing_direction: str = ""
    is_armed: bool = True
    max_distance_since_crossing: float = 0.0


class LineCrossingManager:
    """Manages virtual line crossing detection with directional derivation and anti-duplicate rearm."""

    def __init__(
        self,
        config: Any = None,
        *,
        min_movement: float = 0.008,
        cooldown_seconds: float = 2.0,
        rearm_distance_ratio: float = 0.03,
        max_trajectory_gap_ratio: float = 0.6,
        anchor_type: AnchorType = AnchorType.BOTTOM_CENTER,
    ) -> None:
        if config is not None and hasattr(config, "line_crossing_min_movement"):
            self.min_movement = config.line_crossing_min_movement
            self.cooldown_seconds = config.line_crossing_cooldown_seconds
            self.rearm_distance_ratio = config.line_rearm_distance_ratio
            self.max_trajectory_gap_ratio = getattr(config, "max_trajectory_gap_ratio", 0.6)
            self.anchor_type = config.anchor_type
        else:
            self.min_movement = min_movement
            self.cooldown_seconds = cooldown_seconds
            self.rearm_distance_ratio = rearm_distance_ratio
            self.max_trajectory_gap_ratio = max_trajectory_gap_ratio
            self.anchor_type = anchor_type

        # (camera_id, line_id) -> VirtualLine
        self._lines: dict[tuple[str, str], VirtualLine] = {}
        # (camera_id, track_id, line_id) -> TrackLineState
        self._states: dict[tuple[str, str, str], TrackLineState] = {}
        # Cumulative counts: (camera_id, line_id) -> {"in": int, "out": int}
        self._counts: dict[tuple[str, str], dict[str, int]] = {}

    def set_lines(self, camera_id: str, lines: list[VirtualLine]) -> None:
        """Register or update virtual lines for a camera."""
        old_ids = {lid for (cid, lid) in self._lines if cid == camera_id}
        new_ids = {l.line_id for l in lines}

        # Remove deleted
        for lid in old_ids - new_ids:
            self._lines.pop((camera_id, lid), None)
            for k in list(self._states.keys()):
                if k[0] == camera_id and k[2] == lid:
                    self._states.pop(k, None)

        for l in lines:
            self._lines[(camera_id, l.line_id)] = l
            self._counts.setdefault((camera_id, l.line_id), {"in": 0, "out": 0})

    def get_lines(self, camera_id: str) -> list[VirtualLine]:
        return [l for (cid, _), l in self._lines.items() if cid == camera_id]

    def get_count(self, camera_id: str, line_id: str) -> tuple[int, int]:
        cnt = self._counts.get((camera_id, line_id), {"in": 0, "out": 0})
        return (cnt.get("in", 0), cnt.get("out", 0))

    def get_counts(self, camera_id: str, line_id: str) -> dict[str, int]:
        return dict(self._counts.get((camera_id, line_id), {"in": 0, "out": 0}))

    def get_all_counts(self, camera_id: str) -> dict[str, dict[str, int]]:
        res = {}
        for (cid, lid), cnt in self._counts.items():
            if cid == camera_id:
                res[lid] = dict(cnt)
        return res

    def reset_camera(self, camera_id: str) -> None:
        for k in list(self._states.keys()):
            if k[0] == camera_id:
                self._states.pop(k, None)

    def prune_track(self, camera_id: str, track_id: str) -> None:
        for k in list(self._states.keys()):
            if k[0] == camera_id and k[1] == track_id:
                self._states.pop(k, None)

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
    ) -> list[LineCrossingEvent]:
        """Evaluate anchor movement segment against virtual lines and detect valid crossings."""
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

        events: list[LineCrossingEvent] = []
        now_mono = time.monotonic()

        curr_anchor = bounding_box_anchor(
            bbox_xyxy,
            anchor_type=self.anchor_type,
            width=source_width,
            height=source_height,
        )

        relevant_lines = [
            l for (cid, _), l in self._lines.items()
            if cid == camera_id and l.enabled and (not l.applicable_classes or class_name.lower() in [c.lower() for c in l.applicable_classes])
        ]

        for line in relevant_lines:
            state_key = (camera_id, track_id, line.line_id)
            st = self._states.get(state_key)
            if st is None:
                side = signed_line_side(curr_anchor, line.point_a, line.point_b)
                st = TrackLineState(line_id=line.line_id, last_anchor=curr_anchor, last_side=side)
                self._states[state_key] = st
                continue

            prev_anchor = st.last_anchor
            if prev_anchor is None:
                st.last_anchor = curr_anchor
                st.last_side = signed_line_side(curr_anchor, line.point_a, line.point_b)
                continue

            # Update movement distance
            dx = curr_anchor.x - prev_anchor.x
            dy = curr_anchor.y - prev_anchor.y
            movement = math.hypot(dx, dy)

            # Update rearm tracking distance to line
            curr_dist = distance_point_to_segment(curr_anchor, line.point_a, line.point_b)
            if not st.is_armed:
                st.max_distance_since_crossing = max(st.max_distance_since_crossing, curr_dist)
                # Rearm when moved far enough away from the line
                if st.max_distance_since_crossing >= self.rearm_distance_ratio:
                    st.is_armed = True

            # Reject noisy jitter (below minimum movement) or extreme jumps (tracking jump across frame)
            if movement < self.min_movement or movement > self.max_trajectory_gap_ratio:
                st.last_anchor = curr_anchor
                st.last_side = signed_line_side(curr_anchor, line.point_a, line.point_b)
                continue

            curr_side = signed_line_side(curr_anchor, line.point_a, line.point_b)
            prev_side = st.last_side

            # Segment intersection with virtual line segment
            intersects, inter_point = segment_intersection(
                prev_anchor, curr_anchor, line.point_a, line.point_b
            )

            # A valid crossing requires crossing the line dividing plane (sign flip) and segment intersection
            sign_flip = (prev_side < -1e-6 and curr_side > 1e-6) or (prev_side > 1e-6 and curr_side < -1e-6)

            if intersects and sign_flip and st.is_armed:
                # Determine direction:
                # in_direction specifies which side transition is defined as "IN"
                # By default RIGHT_OF_LINE: transitioning from side > 0 (left/above) to side < 0 (right/below) is IN
                in_is_right = getattr(line, "in_direction", "RIGHT_OF_LINE") in ("RIGHT_OF_LINE", "IN")
                if prev_side > 0 and curr_side < 0:
                    detected_dir = "IN" if in_is_right else "OUT"
                else:
                    detected_dir = "OUT" if in_is_right else "IN"

                crossing_pt = inter_point if inter_point is not None else curr_anchor

                # Directional filtering based on virtual line configuration
                allow_event = False
                if line.direction == CrossingDirection.BIDIRECTIONAL:
                    allow_event = True
                elif line.direction == CrossingDirection.IN and detected_dir == "IN":
                    allow_event = True
                elif line.direction == CrossingDirection.OUT and detected_dir == "OUT":
                    allow_event = True

                if allow_event:
                    # Update counts
                    cnt_key = (camera_id, line.line_id)
                    counts = self._counts.setdefault(cnt_key, {"in": 0, "out": 0})
                    if detected_dir == "IN":
                        counts["in"] += 1
                    else:
                        counts["out"] += 1

                    # Trigger cooldown / disarm
                    st.is_armed = False
                    st.last_crossing_time_mono = now_mono
                    st.last_crossing_direction = detected_dir
                    st.max_distance_since_crossing = 0.0

                    events.append(
                        LineCrossingEvent(
                            event_type="LINE_CROSSING",
                            camera_id=camera_id,
                            track_id=track_id,
                            track_session_id=track_session_id,
                            line_id=line.line_id,
                            crossing_direction=detected_dir,
                            object_class=class_name,
                            timestamp_ns=timestamp_ns,
                            crossing_point=crossing_pt,
                        )
                    )

            st.last_anchor = curr_anchor
            st.last_side = curr_side

        return events
