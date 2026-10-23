from __future__ import annotations

import logging
import time
from typing import Any, Callable
import cv2
import numpy as np

from .types import FrameSample

logger = logging.getLogger(__name__)


class FrameSampler:
    """Collects representative decoded video frames across an observation window.

    - Samples across time (e.g. every 0.5s over 10s) rather than burst frames.
    - Rejects duplicate / static / frozen frames using pixel difference checks.
    - Rejects corrupted / invalid / blank frames.
    - Resizes to bounded analysis resolution (max 640px) to minimize RAM.
    """

    def __init__(
        self,
        sample_count: int = 20,
        sample_duration_seconds: float = 10.0,
        max_resolution: int = 640,
        duplicate_threshold: float = 2.5,  # Mean absolute difference out of 255
        min_diff_threshold: float | None = None,
        max_analysis_dimension: int | None = None,
    ) -> None:
        self.sample_count = max(1, sample_count)
        self.sample_duration_seconds = max(1.0, sample_duration_seconds)
        self.max_resolution = max_analysis_dimension if max_analysis_dimension is not None else max_resolution
        self.duplicate_threshold = min_diff_threshold if min_diff_threshold is not None else duplicate_threshold

    def is_valid_frame(self, img: np.ndarray) -> bool:
        """Check if frame has valid content."""
        return self._is_valid_frame(img)

    def is_duplicate(self, img1: np.ndarray, img2: np.ndarray) -> bool:
        """Check if two frames are near-identical duplicates."""
        thumb1 = cv2.resize(img1, (64, 36), interpolation=cv2.INTER_AREA)
        thumb2 = cv2.resize(img2, (64, 36), interpolation=cv2.INTER_AREA)
        diff = float(np.mean(np.abs(thumb1.astype(np.float32) - thumb2.astype(np.float32))))
        return diff < self.duplicate_threshold

    def preprocess_frame(self, img: np.ndarray) -> np.ndarray:
        """Resize frame to bounded analysis dimensions."""
        return self._resize_bounded(img, self.max_resolution)

    def sample_from_source(
        self,
        source_fn: Callable[[], Any],
        timeout_seconds: float = 10.0,
        camera_id: str = "CAM001",
    ) -> list[FrameSample]:
        """Collect samples from a frame source function."""
        class MockFrame:
            def __init__(self, data: np.ndarray, seq: int) -> None:
                self.image = data
                self.sequence = seq
                self.timestamp = time.time()

        seq = [0]
        def frame_getter(cid: str) -> Any:
            raw = source_fn()
            if raw is None:
                return None
            seq[0] += 1
            if isinstance(raw, np.ndarray):
                return MockFrame(raw, seq[0])
            return raw

        return self.sample_from_store(camera_id, frame_getter)

    def sample_from_store(
        self,
        camera_id: str,
        get_latest_frame_fn: Callable[[str], Any],
        stop_check_fn: Callable[[], bool] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[FrameSample]:
        """Collect representative samples from a camera's decoded frame store across time."""
        interval = self.sample_duration_seconds / float(self.sample_count)
        samples: list[FrameSample] = []
        last_seq = -1
        prev_thumb: np.ndarray | None = None

        start_time = time.monotonic()
        target_time = start_time

        for i in range(self.sample_count):
            if stop_check_fn and stop_check_fn():
                break

            now = time.monotonic()
            elapsed = now - start_time
            if elapsed >= self.sample_duration_seconds:
                break

            # Sleep until target interval time
            sleep_needed = target_time - now
            if sleep_needed > 0:
                time.sleep(sleep_needed)

            target_time += interval

            # Fetch newest frame
            frame = get_latest_frame_fn(camera_id)
            if frame is None:
                continue

            # Extract sequence and image
            seq = getattr(frame, "sequence", -1)
            if seq == last_seq and seq != -1:
                # Same exact sequence from decoder
                continue

            img = self._extract_bgr(frame)
            if img is None or not self._is_valid_frame(img):
                continue

            # Check duplicate / motion against previous sample
            thumb = cv2.resize(img, (64, 36), interpolation=cv2.INTER_AREA)
            if prev_thumb is not None:
                diff = np.mean(np.abs(thumb.astype(np.float32) - prev_thumb.astype(np.float32)))
                if diff < self.duplicate_threshold:
                    # Nearly identical duplicate frame, skip
                    continue

            # Create bounded copy
            bounded_img = self._resize_bounded(img, self.max_resolution)
            ts = getattr(frame, "timestamp", time.time())
            sample = FrameSample(
                camera_id=camera_id,
                sequence=seq,
                timestamp=ts,
                image_bgr=bounded_img,
                width=bounded_img.shape[1],
                height=bounded_img.shape[0],
            )
            samples.append(sample)
            last_seq = seq
            prev_thumb = thumb

            if progress_callback:
                progress_callback(len(samples), self.sample_count)

        logger.info(
            "frame_sampling_complete",
            extra={"camera_id": camera_id, "samples_collected": len(samples), "target": self.sample_count},
        )
        return samples

    def sample_from_images(
        self,
        camera_id: str,
        images: list[np.ndarray],
    ) -> list[FrameSample]:
        """Convenience method for offline or test samples."""
        samples: list[FrameSample] = []
        prev_thumb: np.ndarray | None = None
        t_base = time.time()
        for idx, img in enumerate(images):
            if not self._is_valid_frame(img):
                continue
            thumb = cv2.resize(img, (64, 36), interpolation=cv2.INTER_AREA)
            if prev_thumb is not None:
                diff = np.mean(np.abs(thumb.astype(np.float32) - prev_thumb.astype(np.float32)))
                if diff < self.duplicate_threshold:
                    continue
            prev_thumb = thumb
            bounded = self._resize_bounded(img, self.max_resolution)
            samples.append(
                FrameSample(
                    camera_id=camera_id,
                    sequence=idx,
                    timestamp=t_base + idx * 0.5,
                    image_bgr=bounded,
                    width=bounded.shape[1],
                    height=bounded.shape[0],
                )
            )
            if len(samples) >= self.sample_count:
                break
        return samples

    @staticmethod
    def _extract_bgr(frame: Any) -> np.ndarray | None:
        """Extract BGR numpy array from CameraFrame or GpuFrame."""
        img = getattr(frame, "image", None)
        if img is not None and isinstance(img, np.ndarray):
            return img
        # GpuFrame fallback if tensor exists
        tensor = getattr(frame, "cuda_tensor", None)
        if tensor is not None:
            try:
                # CHW float16/float32 tensor -> HWC BGR uint8
                cpu_t = tensor.detach().cpu().numpy()
                if cpu_t.ndim == 3 and cpu_t.shape[0] == 3:
                    cpu_t = np.transpose(cpu_t, (1, 2, 0))
                if cpu_t.dtype != np.uint8:
                    cpu_t = np.clip(cpu_t * 255.0, 0, 255).astype(np.uint8)
                # If RGB convert to BGR
                return cv2.cvtColor(cpu_t, cv2.COLOR_RGB2BGR)
            except Exception:
                pass
        return None

    @staticmethod
    def _is_valid_frame(img: np.ndarray) -> bool:
        """Check if image array has valid shape and non-corrupted content."""
        if not isinstance(img, np.ndarray) or img.size == 0:
            return False
        if img.ndim != 3 or img.shape[2] != 3:
            return False
        h, w = img.shape[:2]
        if h < 32 or w < 32:
            return False
        # Reject solid black or blown out blank frames
        mean_val = float(np.mean(img))
        if mean_val < 1.0 or mean_val > 254.5:
            return False
        return True

    @staticmethod
    def _resize_bounded(img: np.ndarray, max_dim: int) -> np.ndarray:
        """Resize image keeping aspect ratio such that max dimension <= max_dim."""
        h, w = img.shape[:2]
        if max(h, w) <= max_dim:
            return img.copy()
        scale = max_dim / float(max(h, w))
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        return cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
