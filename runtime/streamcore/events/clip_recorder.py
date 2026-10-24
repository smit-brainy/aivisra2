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
    def __init__(
        self,
        config: EventsConfig,
        camera_rtsp_urls: dict[str, str],
        camera_live_paths: dict[str, str] | None = None,
    ) -> None:
        self.config = config
        self.camera_urls = camera_rtsp_urls
        self.camera_live_paths = camera_live_paths or {}
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

    def _get_candidate_urls(self, camera_id: str) -> list[str]:
        primary_url = self.camera_urls.get(camera_id)
        candidates: list[str] = []
        if primary_url:
            candidates.append(primary_url)
            # TP-Link / Tapo pattern: stream1 -> stream2
            if "/stream1" in primary_url:
                candidates.append(primary_url.replace("/stream1", "/stream2"))
            elif "/stream2" in primary_url:
                candidates.append(primary_url.replace("/stream2", "/stream1"))
            # Hikvision pattern: 101 -> 102
            if "/101" in primary_url:
                candidates.append(primary_url.replace("/101", "/102"))
            elif "/102" in primary_url:
                candidates.append(primary_url.replace("/102", "/101"))
            # Dahua pattern: subtype=0 -> subtype=1
            if "subtype=0" in primary_url:
                candidates.append(primary_url.replace("subtype=0", "subtype=1"))
            elif "subtype=1" in primary_url:
                candidates.append(primary_url.replace("subtype=1", "subtype=0"))
            # Reolink / ONVIF sub patterns
            if "/main" in primary_url:
                candidates.append(primary_url.replace("/main", "/sub"))
            if "/ch01/0" in primary_url:
                candidates.append(primary_url.replace("/ch01/0", "/ch01/1"))

        # Local MediaMTX fallback if running
        live_path = self.camera_live_paths.get(camera_id) or camera_id.lower()
        candidates.append(f"rtsp://127.0.0.1:8554/{live_path}")

        # Deduplicate while preserving order
        seen = set()
        unique_candidates: list[str] = []
        for u in candidates:
            if u not in seen:
                seen.add(u)
                unique_candidates.append(u)
        return unique_candidates

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
        candidate_urls = self._get_candidate_urls(camera_id)
        if not candidate_urls:
            return None

        # Storage convention: clips/{camera_id}/{camera_id}_{YYYYMMDD_HHMMSS}_{event_id}.mp4
        valid_start = start_time if start_time > 1_000_000_000 else time.time()
        timestamp_str = datetime.fromtimestamp(valid_start, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        cam_dir = self.output_dir / camera_id
        cam_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{camera_id}_{timestamp_str}_{event_id}.mp4"
        output_path = cam_dir / filename
        clip_duration = str(getattr(self.config, "clip_duration_seconds", 10))
        timeout_sec = max(20.0, float(clip_duration) + 10.0)

        for candidate_url in candidate_urls:
            # Attempt 1: Fast stream copy with video only (-c:v copy -an)
            # -an prevents container errors with camera audio codecs (like pcm_alaw)
            # -timeout 5000000 ensures socket never hangs on dead streams
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
            if candidate_url.startswith("rtsp://") or candidate_url.startswith("rtsps://"):
                cmd.extend(["-rtsp_transport", "tcp", "-timeout", "5000000"])
            cmd.extend([
                "-i", candidate_url,
                "-t", clip_duration,
                "-c:v", "copy",
                "-an",
                "-avoid_negative_ts", "make_zero",
                "-movflags", "+faststart",
                "-y", str(output_path)
            ])

            try:
                result = subprocess.run(cmd, capture_output=True, timeout=timeout_sec)
                if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
                    rel_path = str(output_path.relative_to(self.output_dir.parent))
                    logger.info("clip_recorded", extra={"camera_id": camera_id, "event_id": event_id, "path": rel_path, "url": candidate_url})
                    return rel_path
                else:
                    if output_path.exists():
                        try:
                            output_path.unlink()
                        except Exception:
                            pass
                    stderr_first = result.stderr.decode(errors="ignore")[:300] if result else ""
                    logger.warning("clip_copy_attempt_failed", extra={
                        "camera_id": camera_id, "event_id": event_id, "url": candidate_url, "stderr": stderr_first
                    })
                    # If stream input failed to open (e.g. session limit or unreachable), skip Attempt 2 on this URL
                    if any(e in stderr_first.lower() for e in [
                        "error opening input", "operation not permitted", "connection refused",
                        "server returned 4", "server returned 5", "method describe failed",
                        "method setup failed", "method play failed", "connection timed out",
                        "immediate exit requested", "end of file", "connection reset by peer"
                    ]):
                        continue

                    # Attempt 2: libx264 ultrafast re-encode fallback on this URL
                    cmd_fallback = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
                    if candidate_url.startswith("rtsp://") or candidate_url.startswith("rtsps://"):
                        cmd_fallback.extend(["-rtsp_transport", "tcp", "-timeout", "5000000"])
                    cmd_fallback.extend([
                        "-i", candidate_url,
                        "-t", clip_duration,
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
                        if output_path.exists():
                            try:
                                output_path.unlink()
                            except Exception:
                                pass
            except subprocess.TimeoutExpired:
                logger.warning("clip_recording_url_timeout", extra={"camera_id": camera_id, "url": candidate_url})
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except Exception:
                        pass
            except Exception as exc:
                if output_path.exists():
                    try:
                        output_path.unlink()
                    except Exception:
                        pass
                logger.warning("clip_recording_url_error", extra={"camera_id": camera_id, "url": candidate_url, "error": str(exc)})

        # If all candidates failed, clean up any partial or corrupt file
        if output_path.exists():
            try:
                output_path.unlink()
            except Exception:
                pass
        logger.error("clip_recording_all_urls_failed", extra={"camera_id": camera_id, "event_id": event_id})
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