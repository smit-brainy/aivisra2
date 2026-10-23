from time import monotonic
from typing import Any

from ..frame_store import LatestFrameStore
from ..types import CameraFrame


class LatestFrameScheduler:
    """Rate-limit each camera and never enqueue historical frames."""

    def __init__(self, camera_ids: list[str], target_fps: float | dict[str, float],
                 max_frame_age_seconds: float) -> None:
        if isinstance(target_fps, (int, float)):
            self.intervals = {camera_id: 1.0 / target_fps for camera_id in camera_ids}
            self.interval = 1.0 / target_fps
        else:
            default_rate = target_fps.get("default", 8.0)
            self.intervals = {
                camera_id: 1.0 / target_fps.get(camera_id, default_rate)
                for camera_id in camera_ids
            }
            self.interval = 1.0 / default_rate
        self.max_age = max_frame_age_seconds
        self.last_sequence = {camera_id: -1 for camera_id in camera_ids}
        self.next_due = {camera_id: 0.0 for camera_id in camera_ids}
        self.replaced_frames = {camera_id: 0 for camera_id in camera_ids}
        self.stale_frames_dropped = {camera_id: 0 for camera_id in camera_ids}
        self.scheduler_skips = {camera_id: 0 for camera_id in camera_ids}
        self._rotation = 0

    def register_camera(self, camera_id: str, target_fps: float | None = None) -> None:
        rate = target_fps if target_fps is not None else (1.0 / self.interval)
        self.intervals[camera_id] = 1.0 / max(0.1, rate)
        self.last_sequence[camera_id] = -1
        self.next_due[camera_id] = 0.0
        self.replaced_frames[camera_id] = 0
        self.stale_frames_dropped[camera_id] = 0
        self.scheduler_skips[camera_id] = 0

    def select(self, store: LatestFrameStore, camera_ids: list[str],
               now: float | None = None, *, respect_rate: bool = True,
               max_batch_size: int | None = None) -> list[Any]:
        now = monotonic() if now is None else now
        limit = max_batch_size if max_batch_size is not None else len(camera_ids)
        ordered = camera_ids[self._rotation:] + camera_ids[:self._rotation]
        self._rotation = (self._rotation + 1) % max(1, len(camera_ids))
        selected: list[Any] = []
        for camera_id in ordered:
            if len(selected) >= limit:
                break
            if respect_rate and now < self.next_due[camera_id]:
                self.scheduler_skips[camera_id] += 1
                continue
            frame = store.latest(camera_id, self.last_sequence[camera_id])
            if frame is None:
                continue
            if now - frame.received_monotonic > self.max_age:
                self.stale_frames_dropped[camera_id] += 1
                if hasattr(frame, "release"):
                    frame.release()
                continue
            previous = self.last_sequence[camera_id]
            if previous >= 0:
                self.replaced_frames[camera_id] += max(0, frame.sequence - previous - 1)
            self.last_sequence[camera_id] = frame.sequence
            self.next_due[camera_id] = now + self.intervals.get(camera_id, self.interval)
            selected.append(frame)
        return selected

    def set_target_fps(self, target_fps: float, camera_id: str | None = None) -> None:
        """Dynamically update target FPS globally or for a specific camera."""
        if target_fps <= 0:
            return
        now = monotonic()
        new_interval = 1.0 / target_fps
        if camera_id is not None:
            self.intervals[camera_id] = new_interval
            if self.next_due.get(camera_id, 0.0) > now + new_interval:
                self.next_due[camera_id] = now + new_interval
        else:
            self.interval = new_interval
            for cid in list(self.intervals.keys()):
                self.intervals[cid] = new_interval
                if self.next_due.get(cid, 0.0) > now + new_interval:
                    self.next_due[cid] = now + new_interval

    def max_target_fps(self) -> float:
        """Return the highest target FPS among all active cameras."""
        if not self.intervals:
            return 1.0 / self.interval if self.interval > 0 else 8.0
        min_int = min(self.intervals.values())
        return (1.0 / min_int) if min_int > 0 else 8.0

    def total_target_fps(self) -> float:
        """Return sum of requested inference rates across all cameras."""
        return sum(1.0 / max(inv, 1e-6) for inv in self.intervals.values())
