import logging
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any, Callable

from ..config import EventsConfig

logger = logging.getLogger("events.clip_recorder")


class ClipRecorder:
    def __init__(self, config: EventsConfig, camera_rtsp_urls: dict[str, str]) -> None:
        self.config = config
        self.camera_urls = camera_rtsp_urls
        self.output_dir = Path(config.clip_storage_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._queue: Queue[tuple[str, str, float, Callable[[str], None] | None]] = Queue()
        self._stop_event = threading.Event()
        self._worker_thread = Thread(target=self._worker_loop, name="clip-recorder", daemon=True)
        self._worker_thread.start()
        logger.info("clip_recorder_started", extra={"max_concurrent": config.max_concurrent_recordings})

    def record_clip(
        self,
        camera_id: str,
        event_id: str,
        start_time: float,
        on_complete: Callable[[str], None] | None = None,
    ) -> None:
        """Non-blocking: queues the recording request."""
        if camera_id not in self.camera_urls:
            logger.warning("clip_recorder_unknown_camera", extra={"camera_id": camera_id})
            return
        self._queue.put((camera_id, event_id, start_time, on_complete))

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                camera_id, event_id, start_time, on_complete = self._queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                clip_path = self._record_sync(camera_id, event_id, start_time)
                if clip_path and on_complete:
                    on_complete(clip_path)
            except Exception as exc:
                logger.error("clip_recording_failed", extra={
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "reason": str(exc)
                })
            finally:
                self._queue.task_done()

    def _record_sync(self, camera_id: str, event_id: str, start_time: float) -> str | None:
        rtsp_url = self.camera_urls.get(camera_id)
        if not rtsp_url:
            return None

        timestamp = datetime.fromtimestamp(start_time, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{camera_id}_{event_id}_{timestamp}.mp4"
        output_path = self.output_dir / filename

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-rtsp_transport", "tcp",
            "-i", rtsp_url,
            "-t", str(self.config.clip_duration_seconds),
            "-c", "copy",
            "-y", str(output_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode == 0 and output_path.exists():
                rel_path = str(output_path.relative_to(self.output_dir.parent))
                logger.info("clip_recorded", extra={"camera_id": camera_id, "event_id": event_id, "path": rel_path})
                return rel_path
            else:
                logger.error("clip_recording_failed", extra={
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "stderr": result.stderr.decode(errors="ignore")[:500]
                })
                return None
        except subprocess.TimeoutExpired:
            logger.error("clip_recording_timeout", extra={"camera_id": camera_id, "event_id": event_id})
            return None
        except Exception as exc:
            logger.error("clip_recording_error", extra={"camera_id": camera_id, "event_id": event_id, "reason": str(exc)})
            return None

    def cleanup_old_clips(self, retention_days: int | None = None) -> int:
        if retention_days is None:
            retention_days = self.config.retention_days

        cutoff_timestamp = time.time() - (retention_days * 86400)
        deleted = 0

        for clip_file in self.output_dir.glob("*.mp4"):
            try:
                stat = clip_file.stat()
                if stat.st_mtime < cutoff_timestamp:
                    clip_file.unlink()
                    deleted += 1
            except Exception as exc:
                logger.warning("clip_cleanup_failed", extra={"path": str(clip_file), "reason": str(exc)})

        if deleted:
            logger.info("clip_cleanup_completed", extra={"deleted": deleted, "retention_days": retention_days})
        return deleted

    def shutdown(self) -> None:
        self._stop_event.set()
        self._worker_thread.join(timeout=5.0)
        if self._worker_thread.is_alive():
            logger.warning("clip_recorder_shutdown_timeout")
        else:
            logger.info("clip_recorder_stopped")