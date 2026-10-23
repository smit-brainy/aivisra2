from __future__ import annotations

import math
from typing import Any
import numpy as np

from ..streamcore.types import Detection
from .best_crop import BestCropSelector
from .track_lifecycle import TrackLifecycle
from .track_store import TrackStore
from .tracker_adapter import BaseTracker
from .types import BestCropMetadata, Direction, Track, TrackState, TrackingConfig


def bbox_xyxy_to_z(bbox: tuple[float, float, float, float]) -> np.ndarray:
    """Convert [x1, y1, x2, y2] to [cx, cy, aspect_ratio, height]."""
    x1, y1, x2, y2 = bbox
    w = max(1e-4, x2 - x1)
    h = max(1e-4, y2 - y1)
    cx = x1 + (w / 2.0)
    cy = y1 + (h / 2.0)
    a = w / h
    return np.array([cx, cy, a, h], dtype=np.float32)


def z_to_bbox_xyxy(z: np.ndarray) -> tuple[float, float, float, float]:
    """Convert [cx, cy, aspect_ratio, height] to [x1, y1, x2, y2]."""
    cx, cy, a, h = float(z[0]), float(z[1]), float(z[2]), float(z[3])
    w = a * h
    return (
        max(0.0, cx - (w / 2.0)),
        max(0.0, cy - (h / 2.0)),
        cx + (w / 2.0),
        cy + (h / 2.0),
    )


class KalmanBoxTracker:
    """Standard 8-state Kalman Filter for bounding box tracking [cx, cy, a, h, vx, vy, va, vh]."""

    def __init__(self, bbox_xyxy: tuple[float, float, float, float]) -> None:
        # State vector [cx, cy, a, h, vx, vy, va, vh]
        self.dim_x = 8
        self.dim_z = 4
        self.x = np.zeros((self.dim_x, 1), dtype=np.float32)
        z = bbox_xyxy_to_z(bbox_xyxy)
        self.x[:4, 0] = z

        # State transition matrix F
        self.F = np.eye(self.dim_x, dtype=np.float32)
        for i in range(4):
            self.F[i, i + 4] = 1.0  # Constant velocity

        # Measurement matrix H
        self.H = np.zeros((self.dim_z, self.dim_x), dtype=np.float32)
        for i in range(4):
            self.H[i, i] = 1.0

        # Covariance matrix P
        self.P = np.eye(self.dim_x, dtype=np.float32) * 10.0
        self.P[4:, 4:] *= 100.0  # High uncertainty in initial velocities

        # Measurement noise covariance R
        self.R = np.eye(self.dim_z, dtype=np.float32)
        self.R[0, 0] = 1.0
        self.R[1, 1] = 1.0
        self.R[2, 2] = 10.0
        self.R[3, 3] = 1.0

        # Process noise covariance Q
        self.Q = np.eye(self.dim_x, dtype=np.float32)
        self.Q[4:, 4:] *= 0.01

    def predict(self) -> tuple[float, float, float, float]:
        """Predict next bounding box state."""
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return z_to_bbox_xyxy(self.x[:4, 0])

    def update(self, bbox_xyxy: tuple[float, float, float, float]) -> None:
        """Update Kalman filter with observation."""
        z = bbox_xyxy_to_z(bbox_xyxy).reshape((self.dim_z, 1))
        y = z - np.dot(self.H, self.x)
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        self.x = self.x + np.dot(K, y)
        self.P = self.P - np.dot(np.dot(K, self.H), self.P)


def compute_iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """Compute IoU between two arrays of bounding boxes [N, 4] and [M, 4]."""
    if len(boxes_a) == 0 or len(boxes_b) == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float32)

    # boxes: [x1, y1, x2, y2]
    a_x1, a_y1, a_x2, a_y2 = boxes_a[:, 0], boxes_a[:, 1], boxes_a[:, 2], boxes_a[:, 3]
    b_x1, b_y1, b_x2, b_y2 = boxes_b[:, 0], boxes_b[:, 1], boxes_b[:, 2], boxes_b[:, 3]

    inter_x1 = np.maximum(a_x1[:, None], b_x1[None, :])
    inter_y1 = np.maximum(a_y1[:, None], b_y1[None, :])
    inter_x2 = np.minimum(a_x2[:, None], b_x2[None, :])
    inter_y2 = np.minimum(a_y2[:, None], b_y2[None, :])

    inter_w = np.maximum(0.0, inter_x2 - inter_x1)
    inter_h = np.maximum(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = np.maximum(0.0, a_x2 - a_x1) * np.maximum(0.0, a_y2 - a_y1)
    area_b = np.maximum(0.0, b_x2 - b_x1) * np.maximum(0.0, b_y2 - b_y1)

    union_area = area_a[:, None] + area_b[None, :] - inter_area
    iou = inter_area / np.maximum(1e-6, union_area)
    return iou.astype(np.float32)


def linear_assignment(
    cost_matrix: np.ndarray,
    cost_limit: float,
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Solve linear sum assignment with a cost threshold."""
    if cost_matrix.size == 0:
        return [], list(range(cost_matrix.shape[0])), list(range(cost_matrix.shape[1]))

    matches = []
    unmatched_a = list(range(cost_matrix.shape[0]))
    unmatched_b = list(range(cost_matrix.shape[1]))

    try:
        import lap
        _, x, y = lap.lapjv(cost_matrix, extend_cost=True, cost_limit=cost_limit)
        for i, j in enumerate(x):
            if j >= 0 and cost_matrix[i, j] <= cost_limit:
                matches.append((i, j))
                if i in unmatched_a:
                    unmatched_a.remove(i)
                if j in unmatched_b:
                    unmatched_b.remove(j)
    except Exception:
        # Fallback to scipy.optimize
        from scipy.optimize import linear_sum_assignment
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
        for r, c in zip(row_ind, col_ind):
            if cost_matrix[r, c] <= cost_limit:
                matches.append((r, c))
                if r in unmatched_a:
                    unmatched_a.remove(r)
                if c in unmatched_b:
                    unmatched_b.remove(c)

    return matches, unmatched_a, unmatched_b


class ByteTrackAdapter(BaseTracker):
    """High-performance CPU ByteTrack implementation with real timestamps and class isolation."""

    def __init__(self, camera_id: str, config: TrackingConfig) -> None:
        super().__init__(camera_id, config)
        self.track_store = TrackStore(camera_id)
        self.store = self.track_store
        self.lifecycle = TrackLifecycle(config)
        self.best_crop_selector = BestCropSelector(config.minimum_crop_improvement)

        self._next_local_id = 1
        self._kalman_filters: dict[int, KalmanBoxTracker] = {}
        self._predicted_boxes: dict[int, tuple[float, float, float, float]] = {}

    def _get_next_id(self) -> int:
        nid = self._next_local_id
        self._next_local_id += 1
        return nid

    def update(
        self,
        detections: list[Detection],
        timestamp_ns: int,
        frame_sequence: int,
        source_width: int,
        source_height: int,
        frame_image: Any = None,
    ) -> list[Track]:
        """Run ByteTrack association and return active tracks."""
        sw = max(1, source_width)
        sh = max(1, source_height)

        # Check elapsed real time for existing active tracks before matching
        for t in self.track_store.active_tracks():
            elapsed_ms = (timestamp_ns - t.last_seen_ns) / 1_000_000.0
            if elapsed_ms >= self.config.end_timeout_ms:
                t.state = TrackState.ENDED
            elif elapsed_ms >= self.config.lost_timeout_ms and t.state == TrackState.CONFIRMED:
                t.state = TrackState.LOST

        # 1. Kalman Prediction for all active tracks
        active_tracks = self.track_store.active_tracks()
        self._predicted_boxes.clear()
        for t in active_tracks:
            kf = self._kalman_filters.get(t.local_track_id)
            if kf is not None:
                self._predicted_boxes[t.local_track_id] = kf.predict()
            else:
                self._predicted_boxes[t.local_track_id] = t.bbox_xyxy

        # 2. Partition detections by class if class_aware is enabled
        if self.config.class_aware:
            class_ids = set(d.class_id for d in detections) | set(t.class_id for t in active_tracks)
            all_matched_track_ids = set()
            for cid in class_ids:
                class_dets = [d for d in detections if d.class_id == cid]
                class_tracks = [t for t in active_tracks if t.class_id == cid]
                matched_ids = self._associate_group(
                    class_tracks,
                    class_dets,
                    timestamp_ns,
                    frame_sequence,
                    sw,
                    sh,
                    frame_image,
                )
                all_matched_track_ids.update(matched_ids)
        else:
            self._associate_group(
                active_tracks,
                detections,
                timestamp_ns,
                frame_sequence,
                sw,
                sh,
                frame_image,
            )

        # 3. Clean up Kalman filters for ended tracks
        self.track_store.prune_ended(max_age_ms=self.config.end_timeout_ms * 2.0, current_timestamp_ns=timestamp_ns)
        active_ids = set(t.local_track_id for t in self.track_store.active_tracks())
        for tid in list(self._kalman_filters.keys()):
            if tid not in active_ids:
                del self._kalman_filters[tid]

        return self.track_store.active_tracks()

    def _associate_group(
        self,
        tracks: list[Track],
        detections: list[Detection],
        timestamp_ns: int,
        frame_sequence: int,
        sw: int,
        sh: int,
        frame_image: Any = None,
    ) -> set[int]:
        """Perform two-stage ByteTrack association for a group of tracks and detections."""
        matched_track_ids: set[int] = set()

        # Unpack detection boxes into unnormalized pixel coordinates
        det_boxes = []
        for d in detections:
            if d.normalized:
                det_boxes.append((d.x1 * sw, d.y1 * sh, d.x2 * sw, d.y2 * sh))
            else:
                det_boxes.append((d.x1, d.y1, d.x2, d.y2))

        # Partition into High and Low confidence detections
        high_indices = [
            i for i, d in enumerate(detections)
            if d.confidence >= self.config.track_high_thresh
        ]
        low_indices = [
            i for i, d in enumerate(detections)
            if self.config.track_low_thresh <= d.confidence < self.config.track_high_thresh
        ]

        # ---------------- Stage 1: Associate Active Tracks with High Detections ----------------
        if tracks and high_indices:
            track_boxes_np = np.array([self._predicted_boxes[t.local_track_id] for t in tracks], dtype=np.float32)
            high_boxes_np = np.array([det_boxes[i] for i in high_indices], dtype=np.float32)
            iou_matrix = compute_iou_matrix(track_boxes_np, high_boxes_np)
            cost_matrix = 1.0 - iou_matrix

            # Distance limit based on match_thresh (cost = 1.0 - iou <= match_thresh)
            cost_limit = float(self.config.match_thresh)
            matches1, unmatched_tracks1_idx, unmatched_high_idx = linear_assignment(cost_matrix, cost_limit)

            for t_idx, h_idx in matches1:
                track = tracks[t_idx]
                det_idx = high_indices[h_idx]
                det = detections[det_idx]
                bbox = det_boxes[det_idx]

                kf = self._kalman_filters.get(track.local_track_id)
                if kf is not None:
                    kf.update(bbox)

                self.lifecycle.register_hit(track, bbox, det.confidence, timestamp_ns)
                self.best_crop_selector.maybe_update(
                    track, bbox, det.confidence, timestamp_ns, frame_sequence, sw, sh, frame_image
                )
                matched_track_ids.add(track.local_track_id)

            unmatched_tracks1 = [tracks[i] for i in unmatched_tracks1_idx]
            unmatched_high_dets = [high_indices[i] for i in unmatched_high_idx]
        else:
            unmatched_tracks1 = list(tracks)
            unmatched_high_dets = list(high_indices)

        # ---------------- Stage 2: Associate Remaining Confirmed Tracks with Low Detections ----------------
        # Only associate confirmed/lost tracks with low-confidence detections (tentative excluded)
        c_tracks = [t for t in unmatched_tracks1 if t.state in (TrackState.CONFIRMED, TrackState.LOST)]
        if c_tracks and low_indices:
            c_boxes_np = np.array([self._predicted_boxes[t.local_track_id] for t in c_tracks], dtype=np.float32)
            low_boxes_np = np.array([det_boxes[i] for i in low_indices], dtype=np.float32)
            iou_matrix = compute_iou_matrix(c_boxes_np, low_boxes_np)
            cost_matrix = 1.0 - iou_matrix

            cost_limit = 1.0 - 0.4  # Relaxed match threshold for recovery
            matches2, unmatched_c_idx, _ = linear_assignment(cost_matrix, cost_limit)

            matched_c_track_ids = set()
            for t_idx, l_idx in matches2:
                track = c_tracks[t_idx]
                det_idx = low_indices[l_idx]
                det = detections[det_idx]
                bbox = det_boxes[det_idx]

                kf = self._kalman_filters.get(track.local_track_id)
                if kf is not None:
                    kf.update(bbox)

                self.lifecycle.register_hit(track, bbox, det.confidence, timestamp_ns)
                self.best_crop_selector.maybe_update(
                    track, bbox, det.confidence, timestamp_ns, frame_sequence, sw, sh, frame_image
                )
                matched_track_ids.add(track.local_track_id)
                matched_c_track_ids.add(track.local_track_id)

            unmatched_tracks2 = [t for t in unmatched_tracks1 if t.local_track_id not in matched_c_track_ids]
        else:
            unmatched_tracks2 = list(unmatched_tracks1)

        # ---------------- Unmatched Tracks: Register Miss ----------------
        for t in unmatched_tracks2:
            self.lifecycle.register_miss(t, timestamp_ns)

        # ---------------- Unmatched High Detections: Create New Tracks ----------------
        for det_idx in unmatched_high_dets:
            det = detections[det_idx]
            bbox = det_boxes[det_idx]
            local_id = self._get_next_id()
            global_id = f"{self.camera_id}:{local_id}"

            new_track = Track(
                camera_id=self.camera_id,
                local_track_id=local_id,
                global_track_id=global_id,
                class_id=det.class_id,
                class_name=det.label,
                confidence=det.confidence,
                bbox_xyxy=bbox,
                first_seen_ns=timestamp_ns,
                last_seen_ns=timestamp_ns,
                duration_ms=0.0,
                state=TrackState.TENTATIVE,
                hit_count=1,
                miss_count=0,
            )
            # Add initial point to trajectory
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            new_track.trajectory.append((cx, cy))
            new_track.trajectory_timestamps.append(timestamp_ns)

            # Initialize Kalman filter
            self._kalman_filters[local_id] = KalmanBoxTracker(bbox)

            # Check initial best crop
            self.best_crop_selector.maybe_update(
                new_track, bbox, det.confidence, timestamp_ns, frame_sequence, sw, sh, frame_image
            )

            self.track_store.put(new_track)
            matched_track_ids.add(local_id)

        return matched_track_ids

    def get_tracks(self) -> list[Track]:
        return self.track_store.all_tracks()

    def reset(self) -> None:
        self.track_store.clear()
        self._kalman_filters.clear()
        self._predicted_boxes.clear()
        self._next_local_id = 1
