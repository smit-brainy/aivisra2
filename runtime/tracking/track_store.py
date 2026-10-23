from __future__ import annotations

from threading import Lock
from typing import Iterator

from .types import Track, TrackState


class TrackStore:
    """Thread-safe, bounded memory track repository per camera."""

    def __init__(self, camera_id: str, max_tracks: int = 500) -> None:
        self.camera_id = camera_id
        self.max_tracks = max_tracks
        self._tracks: dict[int, Track] = {}
        self._lock = Lock()

    def get(self, local_id: int) -> Track | None:
        with self._lock:
            return self._tracks.get(local_id)

    def put(self, track: Track) -> None:
        with self._lock:
            self._tracks[track.local_track_id] = track
            if len(self._tracks) > self.max_tracks:
                self._prune_locked()

    def upsert(self, track: Track) -> None:
        self.put(track)

    def active_tracks(self) -> list[Track]:
        """Return non-ended tracks (TENTATIVE, CONFIRMED, LOST)."""
        with self._lock:
            return [t for t in self._tracks.values() if t.state != TrackState.ENDED]

    def confirmed_tracks(self) -> list[Track]:
        """Return strictly CONFIRMED tracks."""
        with self._lock:
            return [t for t in self._tracks.values() if t.state == TrackState.CONFIRMED]

    def all_tracks(self) -> list[Track]:
        """Return all tracked objects in memory."""
        with self._lock:
            return list(self._tracks.values())

    def prune_ended(self, max_age_ms: float = 30000.0, current_timestamp_ns: int | None = None) -> int:
        """Prune tracks that have been ENDED for longer than max_age_ms."""
        with self._lock:
            removed = 0
            if current_timestamp_ns is None:
                to_del = [tid for tid, t in self._tracks.items() if t.state == TrackState.ENDED]
            else:
                to_del = [
                    tid for tid, t in self._tracks.items()
                    if t.state == TrackState.ENDED and
                    ((current_timestamp_ns - t.last_seen_ns) / 1_000_000.0) > max_age_ms
                ]
            for tid in to_del:
                del self._tracks[tid]
                removed += 1
            return removed

    def _prune_locked(self) -> None:
        """Prune oldest ended or tentative tracks if repository exceeds maximum capacity."""
        ended = sorted(
            [t for t in self._tracks.values() if t.state == TrackState.ENDED],
            key=lambda t: t.last_seen_ns,
        )
        for t in ended:
            del self._tracks[t.local_track_id]
            if len(self._tracks) <= (self.max_tracks * 0.8):
                return

        # If still over limit, prune oldest tentative/lost tracks
        if len(self._tracks) > self.max_tracks:
            removable = sorted(
                [t for t in self._tracks.values() if t.state in (TrackState.TENTATIVE, TrackState.LOST)],
                key=lambda t: t.last_seen_ns,
            )
            for t in removable:
                del self._tracks[t.local_track_id]
                if len(self._tracks) <= (self.max_tracks * 0.8):
                    return

    def clear(self) -> None:
        with self._lock:
            self._tracks.clear()
