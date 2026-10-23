from __future__ import annotations

from collections import deque
import json
import logging
from pathlib import Path
from threading import Lock
import time
from typing import Any

from .types import EventStatus, SpatialEvent

logger = logging.getLogger("intelligence.store")


class EventStore:
    """Abstract interface for event storage and retrieval."""

    def save_event(self, event: SpatialEvent) -> None:
        raise NotImplementedError

    def get_event(self, event_id: str) -> SpatialEvent | None:
        raise NotImplementedError

    def get_active_events(self, camera_id: str | None = None) -> list[SpatialEvent]:
        raise NotImplementedError

    def get_recent_events(self, camera_id: str | None = None, limit: int = 50) -> list[SpatialEvent]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class LocalJsonEventStore(EventStore):
    """Production MVP bounded in-memory event store with append-only JSONL persistence."""

    def __init__(
        self,
        config_or_path: Any = None,
        *,
        storage_path: Any = None,
        max_active: int = 1000,
        max_recent: int = 5000,
        enable_disk: bool = True,
    ) -> None:
        target = storage_path if storage_path is not None else config_or_path
        if target is None:
            target = "config/streamcore/events.jsonl"

        if hasattr(target, "event_storage_path"):
            self.storage_path = Path(target.event_storage_path)
            self.max_active = getattr(target, "max_active_events", max_active)
            self.max_recent = getattr(target, "max_recent_events", max_recent)
            self.enable_disk = enable_disk
        else:
            self.storage_path = Path(target)
            self.max_active = max_active
            self.max_recent = max_recent
            self.enable_disk = enable_disk

        self._lock = Lock()
        # event_id -> SpatialEvent
        self._events_by_id: dict[str, SpatialEvent] = {}
        # active events indexed by deterministic active key (camera_id, track_session_id, track_id, rule_id, geometry_id)
        self._active_events: dict[str, SpatialEvent] = {}
        # Recent events chronological ring buffer
        self._recent_events: deque[SpatialEvent] = deque(maxlen=self.max_recent)

        if self.enable_disk:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load recent historical events on startup without creating false alerts."""
        if not self.storage_path.is_file():
            return

        loaded = 0
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        ev = self._parse_event_dict(data)
                        if ev:
                            self._events_by_id[ev.event_id] = ev
                            self._recent_events.append(ev)
                            # Note: historical events loaded from disk are strictly marked CLOSED or past to prevent false alerts on restart
                            if ev.event_status == EventStatus.OPEN:
                                ev.event_status = EventStatus.CLOSED
                            loaded += 1
                    except Exception:
                        continue
            logger.info("historical_events_loaded", extra={"count": loaded, "path": str(self.storage_path)})
        except Exception as exc:
            logger.warning("event_store_load_failed", extra={"reason": str(exc)})

    def save_event(self, event: SpatialEvent) -> None:
        """Save or update event with thread-safe bounding and JSONL append."""
        with self._lock:
            self._events_by_id[event.event_id] = event

            # Active key
            act_key = f"{event.camera_id}:{event.track_session_id}:{event.track_id}:{event.rule_id}:{event.geometry_id}"

            if event.event_status == EventStatus.OPEN:
                if len(self._active_events) >= self.max_active:
                    # Drop oldest active event to prevent unbounded memory growth
                    oldest_k = next(iter(self._active_events))
                    self._active_events.pop(oldest_k, None)
                self._active_events[act_key] = event
            elif event.event_status == EventStatus.CLOSED:
                self._active_events.pop(act_key, None)

            # Update or push to recent
            # Check if event is already in recent deque
            found = False
            for idx in range(len(self._recent_events) - 1, -1, -1):
                if self._recent_events[idx].event_id == event.event_id:
                    self._recent_events[idx] = event
                    found = True
                    break
            if not found:
                self._recent_events.append(event)

            # Bound _events_by_id dictionary to avoid memory leak
            if len(self._events_by_id) > self.max_recent * 2:
                # Retain only recent event IDs
                recent_ids = {e.event_id for e in self._recent_events}
                recent_ids.update(e.event_id for e in self._active_events.values())
                self._events_by_id = {k: v for k, v in self._events_by_id.items() if k in recent_ids}

        # Disk append outside critical lock (best effort)
        if self.enable_disk:
            try:
                line = json.dumps(event.to_dict()) + "\n"
                with open(self.storage_path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as exc:
                logger.error("event_store_write_failed", extra={"reason": str(exc), "event_id": event.event_id})

    def get_event(self, event_id: str) -> SpatialEvent | None:
        with self._lock:
            return self._events_by_id.get(event_id)

    def get_event(self, event_id: str) -> SpatialEvent | None:
        with self._lock:
            return self._events_by_id.get(event_id)

    def get_active_events(self, camera_id: str | None = None) -> list[SpatialEvent]:
        with self._lock:
            return [
                e for e in self._active_events.values()
                if (camera_id is None or e.camera_id == camera_id) and e.event_status != EventStatus.CLOSED
            ]

    def get_recent_events(self, camera_id: str | None = None, limit: int = 50) -> list[SpatialEvent]:
        with self._lock:
            events = list(self._recent_events)
            if camera_id is not None:
                events = [e for e in events if e.camera_id == camera_id]
            # Return newest first
            return list(reversed(events[-limit:]))

    def _parse_event_dict(self, data: dict[str, Any]) -> SpatialEvent | None:
        try:
            ev = SpatialEvent(
                event_id=data["event_id"],
                event_type=data["event_type"],
                event_status=EventStatus(data.get("event_status", "CLOSED")),
                camera_id=data["camera_id"],
                track_id=data["track_id"],
                track_session_id=data.get("track_session_id", "default"),
                rule_id=data["rule_id"],
                geometry_id=data["geometry_id"],
                object_class=data.get("object_class", "unknown"),
                event_time_utc=data.get("event_time_utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                started_at_utc=data.get("started_at_utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                ended_at_utc=data.get("ended_at_utc"),
                confidence=float(data.get("confidence", 1.0)),
                config_version=int(data.get("config_version", 1)),
                metadata=dict(data.get("metadata", {})),
            )
            return ev
        except Exception:
            return None
