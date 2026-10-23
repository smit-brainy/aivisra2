from __future__ import annotations

from dataclasses import replace
import logging
from threading import Lock
import time
from typing import Any

from ..streamcore.types import Detection, DetectionResult
from .bytetrack_adapter import ByteTrackAdapter
from .metrics import TrackingMetrics
from .tracker_adapter import BaseTracker
from .types import Track, TrackState, TrackingConfig

logger = logging.getLogger("tracking")


def compute_box_iou(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    """Compute IoU between two bounding boxes [x1, y1, x2, y2]."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0
    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])
    union = area_a + area_b - inter_area
    return inter_area / max(1e-6, union)


class TrackerManager:
    """Manages independent ByteTrack instances per camera with isolation and metrics."""

    def __init__(self, config: TrackingConfig) -> None:
        self.config = config
        self.metrics = TrackingMetrics()
        self._trackers: dict[str, BaseTracker] = {}
        self._lock = Lock()
        self._pending_results: dict[str, DetectionResult] = {}

    def get_or_create_tracker(self, camera_id: str) -> BaseTracker:
        with self._lock:
            if camera_id not in self._trackers:
                if self.config.tracker == "bytetrack":
                    self._trackers[camera_id] = ByteTrackAdapter(camera_id, self.config)
                else:
                    self._trackers[camera_id] = ByteTrackAdapter(camera_id, self.config)
            return self._trackers[camera_id]

    def get_tracker(self, camera_id: str) -> BaseTracker:
        return self.get_or_create_tracker(camera_id)

    def process_result(
        self,
        result: DetectionResult,
        frame_image: Any = None,
    ) -> DetectionResult:
        """Process detections for one camera frame, update tracks, and assign track IDs."""
        if not self.config.enabled:
            return result

        start_time = time.monotonic()
        camera_id = result.camera_id

        try:
            tracker = self.get_or_create_tracker(camera_id)
            sw = result.source_width or 1280
            sh = result.source_height or 720
            timestamp_ns = int(result.timestamp * 1_000_000_000)

            # Prior track count
            prior_track_count = len(tracker.get_tracks())

            # Update tracker with detections
            active_tracks = tracker.update(
                detections=list(result.detections),
                timestamp_ns=timestamp_ns,
                frame_sequence=result.frame_sequence,
                source_width=sw,
                source_height=sh,
                frame_image=frame_image,
            )

            # Map track IDs onto Detections
            updated_detections = self._assign_track_ids(result.detections, active_tracks, sw, sh)

            # Metrics bookkeeping
            assoc_ms = (time.monotonic() - start_time) * 1000.0
            e2e_ms = result.total_latency_ms + assoc_ms
            new_tracks_count = max(0, len(tracker.get_tracks()) - prior_track_count)
            ended_tracks_count = sum(1 for t in tracker.get_tracks() if t.state == TrackState.ENDED)

            self.metrics.record_update(
                association_ms=assoc_ms,
                end_to_end_ms=e2e_ms,
                tracks_created=new_tracks_count,
                tracks_ended=ended_tracks_count,
            )

            return replace(
                result,
                detections=tuple(updated_detections),
                total_latency_ms=e2e_ms,
            )

        except Exception as exc:
            self.metrics.record_error()
            logger.error("tracker_update_failed", extra={"camera_id": camera_id, "reason": str(exc)})
            return result

    def _assign_track_ids(
        self,
        detections: tuple[Detection, ...],
        tracks: list[Track],
        sw: int,
        sh: int,
    ) -> list[Detection]:
        """Assign best-matching track_id to each Detection based on bbox overlap."""
        updated: list[Detection] = []
        if not tracks or not detections:
            return list(detections)

        # Build list of active confirmed/tentative track boxes
        for det in detections:
            if det.normalized:
                det_box = (det.x1 * sw, det.y1 * sh, det.x2 * sw, det.y2 * sh)
            else:
                det_box = (det.x1, det.y1, det.x2, det.y2)

            best_iou = 0.0
            best_track: Track | None = None
            for t in tracks:
                if self.config.class_aware and t.class_id != det.class_id:
                    continue
                iou = compute_box_iou(det_box, t.bbox_xyxy)
                if iou > best_iou:
                    best_iou = iou
                    best_track = t

            if best_track is not None and best_iou >= 0.3:
                updated.append(replace(det, track_id=best_track.global_track_id))
            else:
                updated.append(det)

        return updated

    def get_tracks(self, camera_id: str) -> list[Track]:
        """Return all active and confirmed tracks for camera."""
        with self._lock:
            tracker = self._trackers.get(camera_id)
            if tracker is None:
                return []
            return tracker.get_tracks()

    def snapshot_metrics(self) -> dict[str, Any]:
        """Aggregate active/confirmed/lost counts and return full telemetry snapshot."""
        with self._lock:
            active_cnt = 0
            conf_cnt = 0
            lost_cnt = 0
            for t in self._trackers.values():
                for trk in t.get_tracks():
                    if trk.state == TrackState.CONFIRMED:
                        conf_cnt += 1
                        active_cnt += 1
                    elif trk.state == TrackState.TENTATIVE:
                        active_cnt += 1
                    elif trk.state == TrackState.LOST:
                        lost_cnt += 1
                        active_cnt += 1

            return self.metrics.snapshot(
                active_tracks=active_cnt,
                confirmed_tracks=conf_cnt,
                lost_tracks=lost_cnt,
            )

    def reset_camera(self, camera_id: str) -> None:
        with self._lock:
            if camera_id in self._trackers:
                self._trackers[camera_id].reset()
