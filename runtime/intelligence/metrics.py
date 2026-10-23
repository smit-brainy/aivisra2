from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from threading import Lock
import time
from typing import Any


def _calc_percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_v[int(k)])
    d0 = sorted_v[int(f)] * (c - k)
    d1 = sorted_v[int(c)] * (k - f)
    return float(d0 + d1)


class IntelligenceMetrics:
    """Tracks latency, throughput, deduplication, and resource telemetry for spatial intelligence."""

    def __init__(self, window_size: int = 500) -> None:
        self.window_size = window_size
        self._lock = Lock()

        self.spatial_updates_total: int = 0
        self.events_total: int = 0
        self.events_dedup_total: int = 0
        self.duplicate_events_suppressed: int = 0
        self.out_of_order_frames_rejected: int = 0
        self.evidence_captured_total: int = 0

        self._geom_latencies: deque[float] = deque(maxlen=window_size)
        self._rule_latencies: deque[float] = deque(maxlen=window_size)
        self._event_latencies: deque[float] = deque(maxlen=window_size)
        self._total_latencies: deque[float] = deque(maxlen=window_size)

        self._last_snapshot_time = time.monotonic()
        self._last_update_count = 0

    def record_duplicate_event(self) -> None:
        with self._lock:
            self.events_dedup_total += 1
            self.duplicate_events_suppressed += 1

    def record_out_of_order_frame(self) -> None:
        with self._lock:
            self.out_of_order_frames_rejected += 1

    def record_update(
        self,
        geometry_ms: float,
        rule_ms: float,
        event_ms: float,
        events_emitted: int = 0,
        dedup_count: int = 0,
        evidence_count: int = 0,
    ) -> None:
        with self._lock:
            self.spatial_updates_total += 1
            self.events_total += events_emitted
            self.events_dedup_total += dedup_count
            self.evidence_captured_total += evidence_count

            self._geom_latencies.append(geometry_ms)
            self._rule_latencies.append(rule_ms)
            self._event_latencies.append(event_ms)
            self._total_latencies.append(geometry_ms + rule_ms + event_ms)

    def snapshot(
        self,
        active_zone_count: int = 0,
        active_line_count: int = 0,
        active_rule_count: int = 0,
        active_event_count: int = 0,
        queue_depth: int = 0,
    ) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            elapsed = max(0.001, now - self._last_snapshot_time)
            updates_delta = self.spatial_updates_total - self._last_update_count
            updates_per_second = updates_delta / elapsed

            self._last_snapshot_time = now
            self._last_update_count = self.spatial_updates_total

            geom_list = list(self._geom_latencies)
            rule_list = list(self._rule_latencies)
            event_list = list(self._event_latencies)
            total_list = list(self._total_latencies)

            return {
                "spatial_updates_per_second": round(updates_per_second, 2),
                "spatial_updates_total": self.spatial_updates_total,
                "event_count": self.events_total,
                "event_dedup_count": self.events_dedup_total,
                "evidence_capture_count": self.evidence_captured_total,
                "active_zone_count": active_zone_count,
                "active_line_count": active_line_count,
                "active_rule_count": active_rule_count,
                "active_event_count": active_event_count,
                "event_dispatch_queue_depth": queue_depth,
                "latency_ms": {
                    "geometry": {
                        "p50": round(_calc_percentile(geom_list, 50), 3),
                        "p95": round(_calc_percentile(geom_list, 95), 3),
                        "p99": round(_calc_percentile(geom_list, 99), 3),
                    },
                    "rules": {
                        "p50": round(_calc_percentile(rule_list, 50), 3),
                        "p95": round(_calc_percentile(rule_list, 95), 3),
                        "p99": round(_calc_percentile(rule_list, 99), 3),
                    },
                    "events": {
                        "p50": round(_calc_percentile(event_list, 50), 3),
                        "p95": round(_calc_percentile(event_list, 95), 3),
                        "p99": round(_calc_percentile(event_list, 99), 3),
                    },
                    "total": {
                        "p50": round(_calc_percentile(total_list, 50), 3),
                        "p95": round(_calc_percentile(total_list, 95), 3),
                        "p99": round(_calc_percentile(total_list, 99), 3),
                    },
                },
            }
