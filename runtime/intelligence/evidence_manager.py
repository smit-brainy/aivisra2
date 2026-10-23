from __future__ import annotations

import logging
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import time
from typing import Any
import uuid

from .types import EvidenceReference, SpatialEvent

logger = logging.getLogger("intelligence.evidence")


class EvidenceManager:
    """Captures and persists best-crop and snapshot evidence asynchronously without blocking inference."""

    def __init__(
        self,
        config: Any = None,
        *,
        output_dir: str | Path = "runtime/streamcore/output/evidence",
        max_queue_size: int = 100,
    ) -> None:
        if config is not None and hasattr(config, "evidence_storage_dir"):
            self.output_dir = Path(config.evidence_storage_dir)
        elif isinstance(config, (str, Path)):
            self.output_dir = Path(config)
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._queue: Queue[tuple[SpatialEvent, Any, tuple[int, int]]] = Queue(maxsize=max_queue_size)
        self._stop_event = Event()
        self._worker_thread: Thread | None = Thread(
            target=self._worker_loop,
            daemon=True,
            name="evidence_writer",
        )
        self._worker_thread.start()

    def create_evidence_reference(
        self,
        camera_id: str,
        track_id: Any,
        quality_score: float = 0.8,
        bbox: list[float] | None = None,
        crop_filename: str | None = None,
    ) -> EvidenceReference:
        ev_id = f"ev-{uuid.uuid4().hex[:12]}"
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        fname = crop_filename or f"{camera_id}_track{track_id}_{ev_id}.jpg"
        img_path = str(self.output_dir / fname)
        return EvidenceReference(
            evidence_id=ev_id,
            event_id=ev_id,
            camera_id=camera_id,
            track_id=str(track_id),
            capture_timestamp_utc=now_utc,
            bbox=list(bbox or [0.0, 0.0, 0.0, 0.0]),
            image_path=img_path,
            quality_score=quality_score,
            crop_filename=fname,
        )

    def attach_evidence_async(
        self,
        event: SpatialEvent,
        best_crop_metadata: Any = None,
        source_dimensions: tuple[int, int] = (1280, 720),
    ) -> EvidenceReference | None:
        """Create evidence reference immediately and queue image writing asynchronously."""
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ev_id = f"ev-{uuid.uuid4().hex[:12]}"

        bbox = [0.0, 0.0, 0.0, 0.0]
        quality = 0.0
        has_bytes = False

        if best_crop_metadata is not None:
            if hasattr(best_crop_metadata, "bbox_xyxy"):
                bbox = list(best_crop_metadata.bbox_xyxy)
            elif isinstance(best_crop_metadata, dict):
                bbox = list(best_crop_metadata.get("bbox_xyxy", [0.0, 0.0, 0.0, 0.0]))
            quality = getattr(best_crop_metadata, "quality_score", 0.8)
            has_bytes = bool(getattr(best_crop_metadata, "image_bytes", None))

        image_filename = f"{event.camera_id}_{event.event_id}_{ev_id}.jpg" if has_bytes else None
        image_path = str(self.output_dir / image_filename) if image_filename else None

        ref = EvidenceReference(
            evidence_id=ev_id,
            event_id=event.event_id,
            camera_id=event.camera_id,
            track_id=event.track_id,
            capture_timestamp_utc=now_utc,
            bbox=bbox,
            image_path=image_path,
            quality_score=quality,
            source_dimensions=source_dimensions,
        )

        event.evidence_reference = ref

        if has_bytes:
            try:
                self._queue.put_nowait((event, best_crop_metadata, source_dimensions))
            except Exception:
                logger.warning("evidence_queue_full_dropping_image", extra={"event_id": event.event_id})

        return ref

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except Empty:
                continue

            event, best_crop, dims = item
            try:
                self._write_image(event, best_crop)
            except Exception as exc:
                logger.error("evidence_write_failed", extra={"reason": str(exc), "event_id": event.event_id})
            finally:
                self._queue.task_done()

    def _write_image(self, event: SpatialEvent, best_crop: Any) -> None:
        if not event.evidence_reference or not event.evidence_reference.image_path:
            return

        target_file = Path(event.evidence_reference.image_path)
        img_bytes = getattr(best_crop, "image_bytes", None)
        if not img_bytes:
            return

        # Atomic file write
        temp_file = target_file.with_suffix(".tmp")
        temp_file.write_bytes(img_bytes)
        temp_file.replace(target_file)

    def close(self) -> None:
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)

    shutdown = close
