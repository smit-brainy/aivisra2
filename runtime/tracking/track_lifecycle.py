from __future__ import annotations

import math
from typing import Sequence

from .types import Direction, Track, TrackState, TrackingConfig


class TrackLifecycle:
    """Manages track state transitions, timeouts, velocity, and trajectory."""

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config

    def register_hit(
        self,
        track: Track,
        bbox_xyxy: tuple[float, float, float, float],
        confidence: float,
        timestamp_ns: int,
    ) -> None:
        """Update track with a new matched detection."""
        track.bbox_xyxy = bbox_xyxy
        track.confidence = confidence
        track.last_seen_ns = timestamp_ns
        track.duration_ms = max(0.0, (timestamp_ns - track.first_seen_ns) / 1_000_000.0)
        track.hit_count += 1
        track.miss_count = 0

        # State transition
        if track.state == TrackState.TENTATIVE:
            if track.hit_count >= self.config.min_hits_to_confirm:
                track.state = TrackState.CONFIRMED
        elif track.state == TrackState.LOST:
            track.state = TrackState.CONFIRMED

        # Update trajectory and direction
        cx = (bbox_xyxy[0] + bbox_xyxy[2]) / 2.0
        cy = (bbox_xyxy[1] + bbox_xyxy[3]) / 2.0
        track.trajectory.append((cx, cy))
        track.trajectory_timestamps.append(timestamp_ns)

        self._update_motion(track)

    def register_miss(self, track: Track, current_timestamp_ns: int) -> None:
        """Update track when no detection was matched in this frame."""
        track.miss_count += 1
        time_since_last_seen_ms = max(0.0, (current_timestamp_ns - track.last_seen_ns) / 1_000_000.0)

        if track.state == TrackState.TENTATIVE:
            # Tentative tracks that miss immediately are ended faster
            if time_since_last_seen_ms > (self.config.lost_timeout_ms / 2.0):
                track.state = TrackState.ENDED
        elif track.state == TrackState.CONFIRMED:
            if time_since_last_seen_ms >= self.config.lost_timeout_ms:
                track.state = TrackState.LOST
        elif track.state == TrackState.LOST:
            if time_since_last_seen_ms >= self.config.end_timeout_ms:
                track.state = TrackState.ENDED

    def _update_motion(self, track: Track) -> None:
        """Compute instantaneous velocity (px/sec) and movement direction."""
        pts = track.trajectory
        ts = track.trajectory_timestamps
        if len(pts) < 2:
            track.velocity = (0.0, 0.0)
            track.direction = Direction.STATIONARY
            return

        # Use last points over at least ~100ms or up to 5 points for smoothing
        idx_start = max(0, len(pts) - 5)
        dt_s = (ts[-1] - ts[idx_start]) / 1_000_000_000.0
        if dt_s <= 0.001:
            return

        dx = pts[-1][0] - pts[idx_start][0]
        dy = pts[-1][1] - pts[idx_start][1]

        vx = dx / dt_s
        vy = dy / dt_s
        track.velocity = (vx, vy)

        speed = math.hypot(vx, vy)
        if speed < self.config.stationary_threshold_px_s:
            track.direction = Direction.STATIONARY
        elif abs(vx) >= abs(vy):
            track.direction = Direction.RIGHT if vx > 0 else Direction.LEFT
        else:
            track.direction = Direction.DOWN if vy > 0 else Direction.UP

