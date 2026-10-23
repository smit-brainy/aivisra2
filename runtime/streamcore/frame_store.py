from threading import Lock
from typing import Any

from .types import CameraFrame, GpuFrame


class LatestFrameStore:
    """One owned frame per configured camera; no inference backlog.

    Readers must keep sequences increasing across reconnects. Consumers retain
    their own last sequence, allowing independent consumers without destructive reads.
    """

    def __init__(self, camera_ids: list[str]) -> None:
        self._allowed = frozenset(camera_ids)
        self._frames: dict[str, CameraFrame | GpuFrame] = {}
        self._lock = Lock()

    def register_camera(self, camera_id: str) -> None:
        with self._lock:
            self._allowed = self._allowed | {camera_id}

    def put(self, frame: CameraFrame | GpuFrame) -> bool:
        with self._lock:
            if frame.camera_id not in self._allowed:
                raise KeyError(frame.camera_id)
            previous = self._frames.get(frame.camera_id)
            if previous is not None and frame.sequence <= previous.sequence:
                return False
            # If previous frame has a release callback (e.g. GpuFrame), release it
            if previous is not None and hasattr(previous, "release"):
                previous.release()
            self._frames[frame.camera_id] = frame
            return True

    def latest(self, camera_id: str, after_sequence: int = -1) -> CameraFrame | GpuFrame | None:
        with self._lock:
            frame = self._frames.get(camera_id)
            return frame if frame is not None and frame.sequence > after_sequence else None

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)
