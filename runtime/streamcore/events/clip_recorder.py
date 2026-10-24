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
        max_workers = max(1, getattr(config, "max_concurrent_recordings", 2))
        self._workers: list[Thread] = []
        for i in range(max_workers):
            t = Thread(target=self._worker_loop, name=f"clip-recorder-{i}", daemon=True)
            t.start()
            self._workers.append(t)
        logger.info("clip_recorder_started", extra={"max_concurrent": max_workers})

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
                    try:
                        on_complete(clip_path)
                    except Exception as cb_exc:
                        logger.error("clip_completion_callback_failed", extra={
                            "camera_id": camera_id,
                            "event_id": event_id,
                            "reason": str(cb_exc)
                        })
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

        # Storage convention: clips/{camera_id}/{camera_id}_{YYYYMMDD_HHMMSS}_{event_id}.mp4
        valid_start = start_time if start_time > 1_000_000_000 else time.time()
        timestamp_str = datetime.fromtimestamp(valid_start, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        cam_dir = self.output_dir / camera_id
        cam_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{camera_id}_{timestamp_str}_{event_id}.mp4"
        output_path = cam_dir / filename
        timeout_sec = max(25.0, float(self.config.clip_duration_seconds) + 15.0)

        # Primary attempt: stream copy (fast, zero CPU re-encoding)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if rtsp_url.startswith("rtsp://") or rtsp_url.startswith("rtsps://"):
            cmd.extend(["-rtsp_transport", "tcp"])
        cmd.extend([
            "-i", rtsp_url,
            "-t", str(self.config.clip_duration_seconds),
            "-c", "copy",
            "-reset_timestamps", "1",
            "-movflags", "+faststart",
            "-y", str(output_path)
        ])

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout_sec)
            if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                rel_path = str(output_path.relative_to(self.output_dir.parent))
                logger.info("clip_recorded", extra={"camera_id": camera_id, "event_id": event_id, "path": rel_path})
                return rel_path
            else:
                stderr_first = result.stderr.decode(errors="ignore")[:300] if result else ""
                logger.warning("clip_stream_copy_failed_fallback_encoding", extra={
                    "camera_id": camera_id, "event_id": event_id, "stderr": stderr_first
                })
                # Fallback: re-encode with libx264 ultrafast in case stream copy failed on codec/container
                cmd_fallback = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
                if rtsp_url.startswith("rtsp://") or rtsp_url.startswith("rtsps://"):
                    cmd_fallback.extend(["-rtsp_transport", "tcp"])
                cmd_fallback.extend([
                    "-i", rtsp_url,
                    "-t", str(self.config.clip_duration_seconds),
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-an",
                    "-movflags", "+faststart",
                    "-y", str(output_path)
                ])
                res_fallback = subprocess.run(cmd_fallback, capture_output=True, timeout=timeout_sec)
                if res_fallback.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    rel_path = str(output_path.relative_to(self.output_dir.parent))
                    logger.info("clip_recorded_fallback", extra={"camera_id": camera_id, "event_id": event_id, "path": rel_path})
                    return rel_path
                else:
                    stderr_text = res_fallback.stderr.decode(errors="ignore")[:500] if res_fallback else ""
                    logger.error("clip_recording_failed", extra={
                        "camera_id": camera_id,
                        "event_id": event_id,
                        "stderr": stderr_text
                    })
                    if output_path.exists() and output_path.stat().st_size == 0:
                        try:
                            output_path.unlink()
                        except Exception:
                            pass
                    return None
        except subprocess.TimeoutExpired:
            logger.error("clip_recording_timeout", extra={"camera_id": camera_id, "event_id": event_id})
            if output_path.exists() and output_path.stat().st_size == 0:
                try:
                    output_path.unlink()
                except Exception:
                    pass
            return None
        except Exception as exc:
            logger.error("clip_recording_error", extra={"camera_id": camera_id, "event_id": event_id, "reason": str(exc)})
            return None

    def cleanup_old_clips(self, retention_days: int | None = None) -> int:
        if retention_days is None:
            retention_days = self.config.retention_days

        cutoff_timestamp = time.time() - (retention_days * 86400)
        deleted = 0

        for clip_file in self.output_dir.glob("**/*.mp4"):
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
        for t in self._workers:
            t.join(timeout=5.0)
        alive = sum(1 for t in self._workers if t.is_alive())
        if alive > 0:
            logger.warning("clip_recorder_shutdown_timeout", extra={"alive_workers": alive})
        else:
            logger.info("clip_recorder_stopped")