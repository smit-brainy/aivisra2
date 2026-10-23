from __future__ import annotations

from collections import deque
from threading import Lock
import time
from typing import Any
import numpy as np


class TrackingMetrics:
    """Thread-safe telemetry and latency metrics for multi-camera tracking."""

    def __init__(self, window_size: int = 500) -> None:
        self.window_size = window_size
        self._lock = Lock()

        self.tracks_created_total: int = 0
        self.tracks_ended_total: int = 0
        self.tracking_errors: int = 0
        self.best_crop_updates: int = 0

        self._association_latencies: deque[float] = deque(maxlen=window_size)
        self._end_to_end_latencies: deque[float] = deque(maxlen=window_size)

        self._update_count: int = 0
        self._last_rate_time: float = time.monotonic()
        self._last_rate_count: int = 0
        self._current_updates_per_sec: float = 0.0

    def record_update(
        self,
        association_ms: float,
        end_to_end_ms: float,
        tracks_created: int = 0,
        tracks_ended: int = 0,
        best_crop_updated: bool = False,
    ) -> None:
        with self._lock:
            self._update_count += 1
            self._association_latencies.append(association_ms)
            self._end_to_end_latencies.append(end_to_end_ms)
            self.tracks_created_total += tracks_created
            self.tracks_ended_total += tracks_ended
            if best_crop_updated:
                self.best_crop_updates += 1

            now = time.monotonic()
            elapsed = now - self._last_rate_time
            if elapsed >= 1.0:
                self._current_updates_per_sec = (self._update_count - self._last_rate_count) / elapsed
                self._last_rate_time = now
                self._last_rate_count = self._update_count

    def record_error(self) -> None:
        with self._lock:
            self.tracking_errors += 1

    def _calc_percentiles(self, values: deque[float]) -> dict[str, float]:
        if not values:
            return {"avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}
        arr = np.array(values, dtype=np.float32)
        return {
            "avg": round(float(np.mean(arr)), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
        }

    def snapshot(self, active_tracks: int = 0, confirmed_tracks: int = 0, lost_tracks: int = 0) -> dict[str, Any]:
        with self._lock:
            assoc = self._calc_percentiles(self._association_latencies)
            e2e = self._calc_percentiles(self._end_to_end_latencies)
            return {
                "active_tracks": active_tracks,
                "confirmed_tracks": confirmed_tracks,
                "lost_tracks": lost_tracks,
                "tracks_created_total": self.tracks_created_total,
                "tracks_ended_total": self.tracks_ended_total,
                "tracking_updates_per_sec": round(self._current_updates_per_sec, 1),
                "association_latency_ms": assoc,
                "end_to_end_track_latency_ms": e2e,
                "tracking_errors": self.tracking_errors,
                "best_crop_updates": self.best_crop_updates,
            }

