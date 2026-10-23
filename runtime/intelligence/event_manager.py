from __future__ import annotations

import logging
from threading import Lock
import time
from typing import Any
import uuid

from .event_store import EventStore, LocalJsonEventStore
from .evidence_manager import EvidenceManager
from .rule_engine import TriggeredRuleMatch
from .types import EventStatus, Severity, SpatialEvent


logger = logging.getLogger("intelligence.events")


class EventManager:
    """Manages the full lifecycle (OPEN -> UPDATED -> CLOSED) and deterministic deduplication of spatial events."""

    def __init__(
        self,
        event_store_or_config: Any,
        evidence_mgr_or_store: Any = None,
        metrics: Any = None,
    ) -> None:
        if isinstance(event_store_or_config, EventStore):
            self.store = event_store_or_config
            self.evidence_mgr = evidence_mgr_or_store
            self.metrics = metrics
        elif isinstance(evidence_mgr_or_store, EventStore):
            self.store = evidence_mgr_or_store
            self.evidence_mgr = None
            self.metrics = metrics
        else:
            self.store = LocalJsonEventStore()
            self.evidence_mgr = None
            self.metrics = metrics

        self._lock = Lock()
        self._active_events: dict[str, SpatialEvent] = {}
        self._cooldowns: dict[str, float] = {}
        self._last_sequences: dict[str, int] = {}

    def is_sequence_valid(self, camera_id: str, frame_sequence: int) -> bool:
        """Validate sequence monotonicity per camera; reject older or duplicate frames."""
        with self._lock:
            last = self._last_sequences.get(camera_id, -1)
            if frame_sequence <= last and frame_sequence != 0:
                if self.metrics and hasattr(self.metrics, "record_out_of_order_frame"):
                    self.metrics.record_out_of_order_frame()
                return False
            self._last_sequences[camera_id] = frame_sequence
            return True

    def publish_event(
        self,
        camera_id: str,
        rule_id: str,
        rule_name: str,
        rule_type: Any,
        target_id: str,
        track_id: Any,
        status: EventStatus = EventStatus.OPEN,
        severity: Severity = Severity.INFO,
        description: str = "",
        cooldown_seconds: float = 0.0,
        **kwargs: Any,
    ) -> SpatialEvent | None:
        act_key = f"{camera_id}:{track_id}:{rule_id}:{target_id}"
        now_mono = time.monotonic()
        with self._lock:
            last_time = self._cooldowns.get(act_key, 0.0)
            if cooldown_seconds > 0.0 and (now_mono - last_time) < cooldown_seconds:
                if self.metrics and hasattr(self.metrics, "record_duplicate_event"):
                    self.metrics.record_duplicate_event()
                return None
            self._cooldowns[act_key] = now_mono

            now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            event = SpatialEvent(
                event_id=f"evt-{uuid.uuid4().hex[:12]}",
                event_type=str(rule_type),
                event_status=status,
                camera_id=camera_id,
                track_id=str(track_id),
                track_session_id="default",
                rule_id=rule_id,
                geometry_id=target_id,
                object_class="person",
                event_time_utc=now_utc,
                started_at_utc=now_utc,
                ended_at_utc=now_utc if status == EventStatus.CLOSED else None,
                confidence=1.0,
                metadata={"description": description, "severity": str(severity), **kwargs},
            )
            if status != EventStatus.CLOSED:
                self._active_events[event.event_id] = event
            self.store.save_event(event)
            return event

    def update_event(self, event_id: str, description: str = "", dwell_ms: float = 0.0, **kwargs: Any) -> SpatialEvent | None:
        with self._lock:
            event = self.store.get_event(event_id) or self._active_events.get(event_id)
            if event is None:
                return None
            event.event_status = EventStatus.UPDATED
            event.metadata["description"] = description
            event.metadata["dwell_ms"] = dwell_ms
            event.metadata.update(kwargs)
            self.store.save_event(event)
            return event

    def close_event(self, event_id: str, description: str = "", **kwargs: Any) -> SpatialEvent | None:
        with self._lock:
            event = self.store.get_event(event_id) or self._active_events.get(event_id)
            if event is None:
                return None
            event.event_status = EventStatus.CLOSED
            event.ended_at_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            event.metadata["description"] = description
            event.metadata.update(kwargs)
            self._active_events.pop(event_id, None)
            self.store.save_event(event)
            return event

    def process_rule_match(
        self,
        match: TriggeredRuleMatch,
        best_crop_metadata: Any = None,
        source_dimensions: tuple[int, int] = (1280, 720),
        config_version: int = 1,
    ) -> SpatialEvent | None:
        """Process triggered rule match into a new, updated, or finalized event with deduplication."""
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        act_key = f"{match.camera_id}:{match.track_session_id}:{match.track_id}:{match.rule.rule_id}:{match.geometry_id}"

        with self._lock:
            existing = self._active_events.get(act_key)

            # One-time events (e.g. line crossing)
            if "LINE_CROSSED" in match.event_type:
                event = SpatialEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    event_type=match.event_type,
                    event_status=EventStatus.CLOSED,
                    camera_id=match.camera_id,
                    track_id=match.track_id,
                    track_session_id=match.track_session_id,
                    rule_id=match.rule.rule_id,
                    geometry_id=match.geometry_id,
                    object_class=match.object_class,
                    event_time_utc=now_utc,
                    started_at_utc=now_utc,
                    ended_at_utc=now_utc,
                    confidence=1.0,
                    config_version=config_version,
                    metadata=dict(match.metadata),
                )
                if self.evidence_mgr:
                    self.evidence_mgr.attach_evidence_async(event, best_crop_metadata, source_dimensions)
                self.store.save_event(event)
                return event

            # Occupancy thresholds: single closed notification event
            if "OCCUPANCY" in match.event_type:
                event = SpatialEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    event_type=match.event_type,
                    event_status=EventStatus.CLOSED,
                    camera_id=match.camera_id,
                    track_id=match.track_id,
                    track_session_id=match.track_session_id,
                    rule_id=match.rule.rule_id,
                    geometry_id=match.geometry_id,
                    object_class=match.object_class,
                    event_time_utc=now_utc,
                    started_at_utc=now_utc,
                    ended_at_utc=now_utc,
                    confidence=1.0,
                    config_version=config_version,
                    metadata=dict(match.metadata),
                )
                self.store.save_event(event)
                return event

            # Dwell threshold: open or update state
            if match.event_type == "DWELL_THRESHOLD":
                if existing is None:
                    event = SpatialEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:12]}",
                        event_type="DWELL_THRESHOLD",
                        event_status=EventStatus.OPEN,
                        camera_id=match.camera_id,
                        track_id=match.track_id,
                        track_session_id=match.track_session_id,
                        rule_id=match.rule.rule_id,
                        geometry_id=match.geometry_id,
                        object_class=match.object_class,
                        event_time_utc=now_utc,
                        started_at_utc=now_utc,
                        ended_at_utc=None,
                        confidence=1.0,
                        config_version=config_version,
                        metadata=dict(match.metadata),
                    )
                    self._active_events[act_key] = event
                    if self.evidence_mgr:
                        self.evidence_mgr.attach_evidence_async(event, best_crop_metadata, source_dimensions)
                    self.store.save_event(event)
                    return event
                else:
                    # Update existing dwell event
                    existing.event_status = EventStatus.UPDATED
                    existing.metadata.update(match.metadata)
                    self.store.save_event(existing)
                    return existing

            # Zone Enter
            if match.event_type == "ZONE_ENTER":
                if existing is None:
                    event = SpatialEvent(
                        event_id=f"evt-{uuid.uuid4().hex[:12]}",
                        event_type="ZONE_ENTER",
                        event_status=EventStatus.OPEN,
                        camera_id=match.camera_id,
                        track_id=match.track_id,
                        track_session_id=match.track_session_id,
                        rule_id=match.rule.rule_id,
                        geometry_id=match.geometry_id,
                        object_class=match.object_class,
                        event_time_utc=now_utc,
                        started_at_utc=now_utc,
                        ended_at_utc=None,
                        confidence=1.0,
                        config_version=config_version,
                        metadata=dict(match.metadata),
                    )
                    self._active_events[act_key] = event
                    if self.evidence_mgr:
                        self.evidence_mgr.attach_evidence_async(event, best_crop_metadata, source_dimensions)
                    self.store.save_event(event)
                    return event
                return None  # Deduplicated; already open

            # Zone Exit: close any open enter/dwell events for this track/zone
            if match.event_type == "ZONE_EXIT":
                self.close_track_zone_events(match.camera_id, match.track_id, match.geometry_id)
                # Emit standalone ZONE_EXIT event if a rule exists
                event = SpatialEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    event_type="ZONE_EXIT",
                    event_status=EventStatus.CLOSED,
                    camera_id=match.camera_id,
                    track_id=match.track_id,
                    track_session_id=match.track_session_id,
                    rule_id=match.rule.rule_id,
                    geometry_id=match.geometry_id,
                    object_class=match.object_class,
                    event_time_utc=now_utc,
                    started_at_utc=now_utc,
                    ended_at_utc=now_utc,
                    confidence=1.0,
                    config_version=config_version,
                    metadata=dict(match.metadata),
                )
                self.store.save_event(event)
                return event

        return None

    def close_track_zone_events(self, camera_id: str, track_id: str, zone_id: str) -> list[SpatialEvent]:
        """Close any open events associated with a track leaving a zone."""
        closed: list[SpatialEvent] = []
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with self._lock:
            keys_to_close = [
                k for k, ev in self._active_events.items()
                if ev.camera_id == camera_id and ev.track_id == track_id and ev.geometry_id == zone_id
            ]
            for k in keys_to_close:
                ev = self._active_events.pop(k)
                ev.event_status = EventStatus.CLOSED
                ev.ended_at_utc = now_utc
                self.store.save_event(ev)
                closed.append(ev)

        return closed

    def close_track_events(self, camera_id: str, track_id: str) -> list[SpatialEvent]:
        """Close all open events for a track when it ends or is pruned."""
        closed: list[SpatialEvent] = []
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with self._lock:
            keys_to_close = [
                k for k, ev in self._active_events.items()
                if ev.camera_id == camera_id and ev.track_id == track_id
            ]
            for k in keys_to_close:
                ev = self._active_events.pop(k)
                ev.event_status = EventStatus.CLOSED
                ev.ended_at_utc = now_utc
                self.store.save_event(ev)
                closed.append(ev)

        return closed

    def reset_camera(self, camera_id: str) -> None:
        """Close all open events on camera disconnect/reset."""
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            keys_to_close = [
                k for k, ev in self._active_events.items()
                if ev.camera_id == camera_id
            ]
            for k in keys_to_close:
                ev = self._active_events.pop(k)
                ev.event_status = EventStatus.CLOSED
                ev.ended_at_utc = now_utc
                self.store.save_event(ev)
            self._last_sequences.pop(camera_id, None)
