"""One already encoded JPEG per logical camera; reads never encode images."""

from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True, slots=True)
class PreviewImage:
    jpeg: bytes
    sequence: int
    generated_monotonic: float


class PreviewCache:
    def __init__(self, camera_ids: list[str]) -> None:
        self._allowed = frozenset(camera_ids)
        self._latest: dict[str, PreviewImage] = {}
        self._active_until: dict[str, float] = {}
        if camera_ids:
            self._active_until[camera_ids[0]] = monotonic() + 3600.0
        self._lock = Lock()

    def register_camera(self, camera_id: str) -> None:
        with self._lock:
            self._allowed = self._allowed | {camera_id}

    def touch(self, camera_id: str, duration_seconds: float = 3.0) -> None:
        """Mark camera as actively viewed by client."""
        with self._lock:
            self._active_until[camera_id] = monotonic() + duration_seconds

    def is_active(self, camera_id: str) -> bool:
        """Check if camera is currently being actively viewed."""
        with self._lock:
            return monotonic() < self._active_until.get(camera_id, 0.0)

    def put_many(self, camera_ids: list[str], image: PreviewImage) -> None:
        with self._lock:
            for camera_id in camera_ids:
                if camera_id not in self._allowed:
                    raise KeyError(camera_id)
                current = self._latest.get(camera_id)
                if current is None or image.sequence > current.sequence:
                    self._latest[camera_id] = image

    def put(self, camera_id: str, image: PreviewImage) -> None:
        self.put_many([camera_id], image)

    def latest(self, camera_id: str) -> PreviewImage | None:
        with self._lock:
            return self._latest.get(camera_id)

    def age_ms(self, camera_id: str) -> float | None:
        image = self.latest(camera_id)
        return (monotonic() - image.generated_monotonic) * 1000 if image else None

    def all_latest(self) -> dict[str, PreviewImage]:
        with self._lock:
            return dict(self._latest)

    def clear(self) -> None:
        with self._lock:
            self._latest.clear()
            self._active_until.clear()
