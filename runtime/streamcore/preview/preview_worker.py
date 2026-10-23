"""Bounded latest-frame sampler; never runs on a GStreamer reader thread."""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable

from ..config import PreviewConfig
from ..frame_store import LatestFrameStore
from ..metrics import MetricsRegistry
from .preview_cache import PreviewCache, PreviewImage

logger = logging.getLogger(__name__)


class PreviewWorker(Thread):
    def __init__(self, source_groups: dict[str, list[str]], store: LatestFrameStore,
                 cache: PreviewCache, metrics: MetricsRegistry,
                 config: PreviewConfig, stop: Event,
                 results_fn: Callable[[], dict[str, Any]] | None = None) -> None:
        super().__init__(name="preview-worker", daemon=True)
        self.source_groups = source_groups
        self.store = store
        self.cache = cache
        self.metrics = metrics
        self.config = config
        self.stop_event = stop
        self.results_fn = results_fn
        self.last_sequence = {source: -1 for source in source_groups}
        self.last_encode_time = {source: 0.0 for source in source_groups}
        # Parallel thread pool utilizing Ryzen 7 9700X multi-core hardware
        n_workers = min(16, max(4, len(source_groups) // 2))
        self._pool = ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="prev-enc")

    def _encode_source(self, item: tuple[str, list[str]], now: float, results: dict[str, Any], is_large_fleet: bool) -> None:
        import cv2
        source_id, aliases = item
        if self.stop_event.is_set():
            return
        if is_large_fleet:
            is_active = any(self.cache.is_active(cid) for cid in aliases)
            if not is_active and (now - self.last_encode_time.get(source_id, 0.0)) < 0.2:
                return
        frame = self.store.latest(source_id, self.last_sequence[source_id])
        if frame is None:
            return
        if hasattr(frame, "to_bgr_cpu"):
            self.metrics.record_cpu_download(source_id, 1)

        try:
            started = monotonic()
            height, width = frame.image.shape[:2]
            scale = min(self.config.width / width, self.config.height / height, 1)
            if scale < 1:
                target = (max(1, round(width * scale)), max(1, round(height * scale)))
                base_image = cv2.resize(frame.image, target, interpolation=cv2.INTER_LINEAR)
                im_h, im_w = target[1], target[0]
            else:
                base_image = frame.image
                im_h, im_w = height, width

            for camera_id in aliases:
                image = base_image.copy()
                res = results.get(camera_id)
                if res is not None and getattr(res, "detections", None):
                    for det in res.detections:
                        x1 = max(0, min(im_w - 1, int(det.x1 * im_w)))
                        y1 = max(0, min(im_h - 1, int(det.y1 * im_h)))
                        x2 = max(0, min(im_w - 1, int(det.x2 * im_w)))
                        y2 = max(0, min(im_h - 1, int(det.y2 * im_h)))
                        color = (0, 255, 0) if det.class_id == 0 else (0, 215, 255) if det.class_id in (2, 3, 5, 7) else (255, 180, 0)
                        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                        id_str = f" ID {det.track_id.split(':')[-1]}" if getattr(det, "track_id", None) else ""
                        label = f"{det.label}{id_str} {det.confidence:.2f}"
                        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                        cv2.rectangle(image, (x1, max(0, y1 - th - 4)), (x1 + tw + 2, y1), color, -1)
                        cv2.putText(image, label, (x1 + 1, max(th, y1 - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)

                success, encoded = cv2.imencode(
                    ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, self.config.jpeg_quality])
                if not success:
                    raise RuntimeError("JPEG encode failed")
                finished = monotonic()
                preview = PreviewImage(encoded.tobytes(), frame.sequence, finished)
                self.cache.put(camera_id, preview)
                self.metrics.preview_published(camera_id, frame.sequence, finished)

            finished = monotonic()
            self.metrics.preview_encoded((finished - started) * 1000)
            self.last_sequence[source_id] = frame.sequence
            self.last_encode_time[source_id] = now
        except Exception as exc:
            logger.warning("preview_encode_failed", extra={"camera_id": source_id,
                          "reason": type(exc).__name__})

    def tick(self) -> None:
        now = monotonic()
        results = self.results_fn() if self.results_fn is not None else {}
        is_large_fleet = len(self.source_groups) > 8
        items = sorted(
            self.source_groups.items(),
            key=lambda it: not any(self.cache.is_active(cid) for cid in it[1]),
        )

        # Parallelize across workers in the thread pool for high-throughput multi-camera encoding
        futures = [self._pool.submit(self._encode_source, item, now, results, is_large_fleet) for item in items]
        for f in futures:
            if self.stop_event.is_set():
                break
            try:
                f.result()
            except Exception:
                pass

    def close(self) -> None:
        self._pool.shutdown(wait=False)

    def run(self) -> None:
        period = 1 / self.config.fps
        while not self.stop_event.is_set():
            started = monotonic()
            self.tick()
            self.stop_event.wait(max(0, started + period - monotonic()))
