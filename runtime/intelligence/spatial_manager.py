from __future__ import annotations

import json
import logging
from pathlib import Path
import tempfile
from threading import Lock
import time
from typing import Any
import uuid

from .config import SpatialConfig
from .dwell_manager import DwellManager
from .event_manager import EventManager
from .event_store import EventStore, LocalJsonEventStore
from .evidence_manager import EvidenceManager
from .geometry import line_validation, polygon_validation
from .line_crossing import LineCrossingManager
from .metrics import IntelligenceMetrics
from .occupancy_manager import OccupancyManager
from .rule_engine import RuleEngine, TriggeredRuleMatch
from .types import OccupancyState, PolygonZone, RuleType, Severity, SpatialEvent, SpatialRule, VirtualLine
from .zone_manager import ZoneManager

logger = logging.getLogger("intelligence.manager")


class SpatialManager:
    """Production coordinator for spatial geometry, rules, dwell, occupancy, events, and evidence."""

    def __init__(
        self,
        config: SpatialConfig | None = None,
        event_store: EventStore | None = None,
        evidence_manager: EvidenceManager | None = None,
    ) -> None:
        self.config = config or SpatialConfig()
        self.store = event_store or LocalJsonEventStore(
            storage_path=self.config.event_storage_path,
            max_active=self.config.max_active_events,
            max_recent=self.config.max_recent_events,
        )
        self.evidence_mgr = evidence_manager or EvidenceManager(
            output_dir=self.config.evidence_storage_dir
        )
        self.metrics = IntelligenceMetrics()
        self.event_mgr = EventManager(self.store, self.evidence_mgr, self.metrics)

        self.zone_mgr = ZoneManager(
            entry_confirmations=self.config.entry_confirmation_updates,
            exit_confirmations=self.config.exit_confirmation_updates,
            boundary_margin_ratio=self.config.boundary_margin_ratio,
            anchor_type=self.config.anchor_type,
        )
        self.line_mgr = LineCrossingManager(
            min_movement=self.config.line_crossing_min_movement,
            cooldown_seconds=self.config.line_crossing_cooldown_seconds,
            rearm_distance_ratio=self.config.line_rearm_distance_ratio,
            max_trajectory_gap_ratio=self.config.max_trajectory_gap_ratio,
            anchor_type=self.config.anchor_type,
        )
        self.dwell_mgr = DwellManager(occlusion_grace_ms=self.config.dwell_occlusion_grace_ms)
        self.occupancy_mgr = OccupancyManager()
        self.rule_engine = RuleEngine()

        self._lock = Lock()
        # camera_id -> config version
        self._versions: dict[str, int] = {}
        # camera_id -> session epoch id
        self._sessions: dict[str, str] = {}
        # camera_id -> set of active track IDs
        self._active_track_ids_per_cam: dict[str, set[str]] = {}

        self.rules_file = Path(self.config.spatial_rules_path)
        self._load_configuration()

    def _load_configuration(self) -> None:
        """Load persistent spatial configuration from spatial_rules.json."""
        if not self.rules_file.is_file():
            return
        try:
            with open(self.rules_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for cam_id, cam_cfg in data.items():
                version = int(cam_cfg.get("version", 1))
                self._versions[cam_id] = version

                zones = [PolygonZone.from_dict({**z, "camera_id": cam_id}) for z in cam_cfg.get("zones", [])]
                lines = [VirtualLine.from_dict({**l, "camera_id": cam_id}) for l in cam_cfg.get("lines", [])]
                rules = [SpatialRule.from_dict({**r, "camera_id": cam_id}) for r in cam_cfg.get("rules", [])]

                self.zone_mgr.set_zones(cam_id, zones)
                self.line_mgr.set_lines(cam_id, lines)
                self.rule_engine.set_rules(cam_id, rules)

            logger.info("spatial_configuration_loaded", extra={"cameras": list(data.keys())})
        except Exception as exc:
            logger.error("spatial_configuration_load_failed", extra={"reason": str(exc)})

    def _persist_configuration(self) -> None:
        """Atomically persist spatial configuration to JSON file."""
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}

        all_cams = set(self._versions.keys())
        for (cid, _) in self.zone_mgr._zones.keys():
            all_cams.add(cid)
        for (cid, _) in self.line_mgr._lines.keys():
            all_cams.add(cid)
        for (cid, _) in self.rule_engine._rules.keys():
            all_cams.add(cid)

        for cid in sorted(all_cams):
            data[cid] = {
                "version": self._versions.get(cid, 1),
                "zones": [z.to_dict() for z in self.zone_mgr.get_zones(cid)],
                "lines": [l.to_dict() for l in self.line_mgr.get_lines(cid)],
                "rules": [r.to_dict() for r in self.rule_engine.get_rules(cid)],
            }

        temp_file = self.rules_file.with_suffix(f".tmp.{time.time_ns()}")
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_file.replace(self.rules_file)

    _save_all_configurations = _persist_configuration

    def get_config_version(self, camera_id: str) -> int:
        return self._versions.get(camera_id, 1)

    def get_camera_session(self, camera_id: str) -> str:
        if camera_id not in self._sessions:
            self._sessions[camera_id] = f"sess_{int(time.time_ns())}"
        return self._sessions[camera_id]

    get_session_epoch = get_camera_session

    def reset_camera(self, camera_id: str) -> None:
        """Cleanly handle camera disconnect/reconnect."""
        with self._lock:
            # Generate new session epoch to prevent track ID collisions across reconnect
            self._sessions[camera_id] = f"sess_{int(time.time_ns())}_{uuid.uuid4().hex[:6]}"
            self._active_track_ids_per_cam.pop(camera_id, None)
            self.zone_mgr.reset_camera(camera_id)
            self.line_mgr.reset_camera(camera_id)
            self.dwell_mgr.reset_camera(camera_id)
            self.occupancy_mgr.reset_camera(camera_id)
            self.event_mgr.reset_camera(camera_id)

    def handle_camera_disconnect(self, camera_id: str) -> None:
        self.reset_camera(camera_id)

    def handle_camera_connect(self, camera_id: str) -> None:
        with self._lock:
            self._sessions[camera_id] = f"sess_{int(time.time_ns())}_{uuid.uuid4().hex[:6]}"

    # ───────────────────────────── Atomic Config Updates ─────────────────────────────

    def update_zones(self, camera_id: str, zones_data: list[dict[str, Any]], expected_version: int | None = None) -> tuple[bool, str, int]:
        """Atomically validate, reconcile, apply, and persist zones."""
        with self._lock:
            current_ver = self._versions.get(camera_id, 1)
            if expected_version is not None and expected_version != current_ver:
                return False, f"Version conflict: expected {expected_version}, current {current_ver}", current_ver

            # Validate all geometry
            new_zones: list[PolygonZone] = []
            for zd in zones_data:
                try:
                    z = PolygonZone.from_dict({**zd, "camera_id": camera_id})
                    ok, msg = polygon_validation(z.polygon)
                    if not ok:
                        return False, f"Zone '{z.name}' ({z.zone_id}) validation error: {msg}", current_ver
                    new_zones.append(z)
                except Exception as exc:
                    return False, f"Invalid zone schema: {exc}", current_ver

            # Apply
            self.zone_mgr.set_zones(camera_id, new_zones)
            new_ver = current_ver + 1
            self._versions[camera_id] = new_ver
            self._persist_configuration()
            return True, "Zones updated successfully", new_ver

    def update_lines(self, camera_id: str, lines_data: list[dict[str, Any]], expected_version: int | None = None) -> tuple[bool, str, int]:
        """Atomically validate, reconcile, apply, and persist virtual lines."""
        with self._lock:
            current_ver = self._versions.get(camera_id, 1)
            if expected_version is not None and expected_version != current_ver:
                return False, f"Version conflict: expected {expected_version}, current {current_ver}", current_ver

            new_lines: list[VirtualLine] = []
            for ld in lines_data:
                try:
                    l = VirtualLine.from_dict({**ld, "camera_id": camera_id})
                    ok, msg = line_validation(l.point_a, l.point_b)
                    if not ok:
                        return False, f"Line '{l.name}' ({l.line_id}) validation error: {msg}", current_ver
                    new_lines.append(l)
                except Exception as exc:
                    return False, f"Invalid line schema: {exc}", current_ver

            self.line_mgr.set_lines(camera_id, new_lines)
            new_ver = current_ver + 1
            self._versions[camera_id] = new_ver
            self._persist_configuration()
            return True, "Lines updated successfully", new_ver

    def update_rules(self, camera_id: str, rules_data: list[dict[str, Any]], expected_version: int | None = None) -> tuple[bool, str, int]:
        """Atomically validate, apply, and persist rules."""
        with self._lock:
            current_ver = self._versions.get(camera_id, 1)
            if expected_version is not None and expected_version != current_ver:
                return False, f"Version conflict: expected {expected_version}, current {current_ver}", current_ver

            # Verify target geometry exists for each rule
            existing_zones = {z.zone_id for z in self.zone_mgr.get_zones(camera_id)}
            existing_lines = {l.line_id for l in self.line_mgr.get_lines(camera_id)}

            new_rules: list[SpatialRule] = []
            for rd in rules_data:
                try:
                    r = SpatialRule.from_dict({**rd, "camera_id": camera_id})
                    if r.rule_type in (RuleType.ZONE_ENTER, RuleType.ZONE_EXIT, RuleType.DWELL_THRESHOLD):
                        if r.target_geometry_id and r.target_geometry_id not in existing_zones:
                            return False, f"Rule '{r.name}' targets non-existent zone '{r.target_geometry_id}'", current_ver
                    elif r.rule_type == RuleType.LINE_CROSSING:
                        if r.target_geometry_id and r.target_geometry_id not in existing_lines:
                            return False, f"Rule '{r.name}' targets non-existent line '{r.target_geometry_id}'", current_ver

                    new_rules.append(r)
                except Exception as exc:
                    return False, f"Invalid rule schema: {exc}", current_ver

            self.rule_engine.set_rules(camera_id, new_rules)
            new_ver = current_ver + 1
            self._versions[camera_id] = new_ver
            self._persist_configuration()
            return True, "Rules updated successfully", new_ver

    # ───────────────────────────── Track Processing Pipeline ─────────────────────────────

    def process_tracks(
        self,
        camera_id: str,
        tracks: list[Any],
        *args: Any,
        frame_sequence: int = 0,
        source_width: int = 1280,
        source_height: int = 720,
        timestamp_ns: int = 0,
        **kwargs: Any,
    ) -> list[SpatialEvent]:
        """Sequential per-camera spatial pipeline evaluating geometry, transitions, rules, and events."""
        if len(args) == 2:
            frame_sequence = int(args[0])
            timestamp_ns = int(args[1])
        elif len(args) == 4:
            frame_sequence = int(args[0])
            source_width = int(args[1])
            source_height = int(args[2])
            timestamp_ns = int(args[3])
        elif kwargs:
            frame_sequence = int(kwargs.get("frame_sequence", frame_sequence))
            source_width = int(kwargs.get("source_width", source_width))
            source_height = int(kwargs.get("source_height", source_height))
            timestamp_ns = int(kwargs.get("timestamp_ns", timestamp_ns))

        if not self.event_mgr.is_sequence_valid(camera_id, frame_sequence):
            return []

        t0 = time.monotonic()
        emitted_events: list[SpatialEvent] = []
        track_session_id = self.get_camera_session(camera_id)
        config_version = self.get_config_version(camera_id)

        all_matches: list[TriggeredRuleMatch] = []
        best_crop_map: dict[str, Any] = {}

        # 0. Detect and prune disappeared tracks
        current_track_ids = {
            str(getattr(trk, "global_track_id", getattr(trk, "track_id", getattr(trk, "local_track_id", "0"))))
            for trk in tracks
        }
        prev_track_ids = self._active_track_ids_per_cam.get(camera_id, set())
        disappeared_track_ids = prev_track_ids - current_track_ids
        for tid in disappeared_track_ids:
            exit_evts = self.zone_mgr.prune_track(camera_id, tid)
            for z_evt in exit_evts:
                self.dwell_mgr.on_zone_exit(camera_id, tid, z_evt.zone_id)
                all_matches.extend(self.rule_engine.evaluate_zone_event(z_evt))
            self.line_mgr.prune_track(camera_id, tid)
            self.event_mgr.close_track_events(camera_id, tid)
        self._active_track_ids_per_cam[camera_id] = current_track_ids

        # 1. Update tracks through geometry managers
        for trk in tracks:
            track_id = str(getattr(trk, "global_track_id", getattr(trk, "track_id", getattr(trk, "local_track_id", "0"))))
            class_name = getattr(trk, "class_name", "person")
            bbox = getattr(trk, "bbox_xyxy", (0.0, 0.0, 0.0, 0.0))
            track_state = str(getattr(trk, "track_state", getattr(trk, "state", "CONFIRMED")))
            source_width = getattr(trk, "frame_width", getattr(trk, "source_width", source_width))
            source_height = getattr(trk, "frame_height", getattr(trk, "source_height", source_height))
            best_crop = getattr(trk, "best_crop_metadata", None)
            if best_crop:
                best_crop_map[track_id] = best_crop

            # A. Zone Evaluation
            zone_transitions = self.zone_mgr.update_track(
                camera_id=camera_id,
                track_id=track_id,
                class_name=class_name,
                bbox_xyxy=bbox,
                source_width=source_width,
                source_height=source_height,
                timestamp_ns=timestamp_ns,
                track_session_id=track_session_id,
                track_state=track_state,
            )

            for z_evt in zone_transitions:
                if z_evt.event_type == "ZONE_ENTER":
                    self.dwell_mgr.on_zone_enter(
                        camera_id=camera_id,
                        track_id=track_id,
                        track_session_id=track_session_id,
                        zone_id=z_evt.zone_id,
                        object_class=z_evt.object_class,
                        timestamp_ns=timestamp_ns,
                        anchor_point=z_evt.anchor_point,
                    )
                elif z_evt.event_type == "ZONE_EXIT":
                    self.dwell_mgr.on_zone_exit(camera_id, track_id, z_evt.zone_id)

                matches = self.rule_engine.evaluate_zone_event(z_evt)
                all_matches.extend(matches)

            # Update dwell presence & check dwell thresholds for active zones
            for zone in self.zone_mgr.get_zones(camera_id):
                self.dwell_mgr.update_presence(
                    camera_id=camera_id,
                    track_id=track_id,
                    zone_id=zone.zone_id,
                    anchor_point=zone_transitions[0].anchor_point if zone_transitions else self.zone_mgr._states.get((camera_id, track_id, zone.zone_id), getattr(self.zone_mgr, "last_anchor", None)),
                    track_state=track_state,
                )
                # Find dwell rules targeting this zone
                dwell_rules = [
                    r for r in self.rule_engine.get_rules(camera_id)
                    if r.enabled and r.rule_type == RuleType.DWELL_THRESHOLD and (not r.target_geometry_id or r.target_geometry_id == zone.zone_id)
                ]
                for dr in dwell_rules:
                    thresh = dr.threshold if dr.threshold > 0 else float(dr.conditions.get("minimum_duration_seconds", 0.0))
                    dwell_evts = self.dwell_mgr.check_thresholds(
                        camera_id=camera_id,
                        track_id=track_id,
                        track_session_id=track_session_id,
                        zone_id=zone.zone_id,
                        threshold_seconds=thresh,
                        timestamp_ns=timestamp_ns,
                    )
                    for devt in dwell_evts:
                        all_matches.extend(self.rule_engine.evaluate_dwell_event(devt))

            # B. Virtual Line Evaluation
            line_crossings = self.line_mgr.update_track(
                camera_id=camera_id,
                track_id=track_id,
                class_name=class_name,
                bbox_xyxy=bbox,
                source_width=source_width,
                source_height=source_height,
                timestamp_ns=timestamp_ns,
                track_session_id=track_session_id,
                track_state=track_state,
            )

            for l_evt in line_crossings:
                # Update flow occupancy counter
                self.occupancy_mgr.on_line_crossing(camera_id, l_evt.crossing_direction)
                matches = self.rule_engine.evaluate_line_event(l_evt)
                all_matches.extend(matches)

        # C. Update Visible Zone Occupancy per zone
        for zone in self.zone_mgr.get_zones(camera_id):
            inside_tids = self.zone_mgr.get_tracks_inside_zone(camera_id, zone.zone_id)
            self.occupancy_mgr.on_zone_presence_update(camera_id, zone.zone_id, inside_tids)

        t_geom = time.monotonic()
        geom_ms = (t_geom - t0) * 1000.0

        # D. Occupancy Threshold Rules
        vis_occ = self.occupancy_mgr.get_visible_occupancy(camera_id)
        occ_matches = self.rule_engine.evaluate_occupancy_threshold(
            camera_id=camera_id,
            occupancy_type="VISIBLE",
            current_count=vis_occ,
            timestamp_ns=timestamp_ns,
        )
        all_matches.extend(occ_matches)

        t_rule = time.monotonic()
        rule_ms = (t_rule - t_geom) * 1000.0

        # E. Event Generation & Deduplication
        dedup_count = 0
        evidence_count = 0
        for match in all_matches:
            crop = best_crop_map.get(match.track_id)
            ev = self.event_mgr.process_rule_match(
                match=match,
                best_crop_metadata=crop,
                source_dimensions=(source_width, source_height),
                config_version=config_version,
            )
            if ev is not None:
                emitted_events.append(ev)
                if ev.evidence_reference:
                    evidence_count += 1
            else:
                dedup_count += 1

        t_event = time.monotonic()
        event_ms = (t_event - t_rule) * 1000.0

        # Record metrics
        self.metrics.record_update(
            geometry_ms=geom_ms,
            rule_ms=rule_ms,
            event_ms=event_ms,
            events_emitted=len(emitted_events),
            dedup_count=dedup_count,
            evidence_count=evidence_count,
        )

        return emitted_events

    def get_telemetry_snapshot(self) -> dict[str, Any]:
        """Aggregate spatial metrics and active resource counts."""
        active_zones = sum(len(self.zone_mgr.get_zones(c)) for c in self._versions)
        active_lines = sum(len(self.line_mgr.get_lines(c)) for c in self._versions)
        active_rules = sum(len(self.rule_engine.get_rules(c)) for c in self._versions)
        active_events = len(self.store.get_active_events())
        queue_depth = self.evidence_mgr._queue.qsize() if hasattr(self.evidence_mgr, "_queue") else 0

        return self.metrics.snapshot(
            active_zone_count=active_zones,
            active_line_count=active_lines,
            active_rule_count=active_rules,
            active_event_count=active_events,
            queue_depth=queue_depth,
        )

    def close(self) -> None:
        if self.evidence_mgr:
            self.evidence_mgr.close()
