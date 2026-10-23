from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any

from .dwell_manager import DwellEvent
from .line_crossing import LineCrossingEvent
from .types import Point, RuleType, Severity, SpatialRule
from .zone_manager import ZoneTransitionEvent

logger = logging.getLogger("intelligence.rules")


@dataclass
class TriggeredRuleMatch:
    rule: SpatialRule
    camera_id: str
    track_id: str
    track_session_id: str
    geometry_id: str
    object_class: str
    event_type: str
    timestamp_ns: int
    anchor_point: Point
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        return self.rule.rule_id

    @property
    def severity(self) -> Severity:
        return self.rule.severity


class RuleEngine:
    """Configuration-driven rule evaluator with strictly typed criteria and cooldowns."""

    def __init__(self, config: Any = None) -> None:
        self.config = config
        # (camera_id, rule_id) -> SpatialRule
        self._rules: dict[tuple[str, str], SpatialRule] = {}
        # (camera_id, rule_id, track_id_or_global) -> last_triggered_monotonic
        self._cooldowns: dict[tuple[str, str, str], float] = {}

    def set_rules(self, camera_id: str, rules: list[SpatialRule]) -> None:
        """Register or update rules for a camera."""
        old_ids = {rid for (cid, rid) in self._rules if cid == camera_id}
        new_ids = {r.rule_id for r in rules}

        for rid in old_ids - new_ids:
            self._rules.pop((camera_id, rid), None)
            for k in list(self._cooldowns.keys()):
                if k[0] == camera_id and k[1] == rid:
                    self._cooldowns.pop(k, None)

        for r in rules:
            self._rules[(camera_id, r.rule_id)] = r

    def get_rules(self, camera_id: str) -> list[SpatialRule]:
        return [r for (cid, _), r in self._rules.items() if cid == camera_id]

    def get_rule(self, camera_id: str, rule_id: str) -> SpatialRule | None:
        return self._rules.get((camera_id, rule_id))

    def evaluate_zone_transition(self, camera_id: str, event_type: str, zone_id: str, track_id: Any) -> list[TriggeredRuleMatch]:
        from .zone_manager import ZoneTransitionEvent
        evt = ZoneTransitionEvent(
            camera_id=camera_id,
            track_id=str(track_id),
            track_session_id="default",
            zone_id=zone_id,
            object_class="person",
            event_type=event_type,
            timestamp_ns=time.monotonic_ns(),
            anchor_point=Point(0.0, 0.0),
        )
        return self.evaluate_zone_event(evt)

    def evaluate_line_crossing(self, camera_id: str, line_id: str, direction: str, track_id: Any) -> list[TriggeredRuleMatch]:
        from .line_crossing import LineCrossingEvent
        evt = LineCrossingEvent(
            camera_id=camera_id,
            track_id=str(track_id),
            track_session_id="default",
            line_id=line_id,
            object_class="person",
            direction=direction,
            timestamp_ns=time.monotonic_ns(),
            crossing_point=Point(0.0, 0.0),
        )
        return self.evaluate_line_event(evt)

    def evaluate_zone_event(self, event: ZoneTransitionEvent) -> list[TriggeredRuleMatch]:
        """Evaluate rules applicable to ZONE_ENTER or ZONE_EXIT transitions."""
        matches: list[TriggeredRuleMatch] = []
        now_mono = time.monotonic()

        target_type = RuleType.ZONE_ENTER if event.event_type == "ZONE_ENTER" else RuleType.ZONE_EXIT

        relevant_rules = [
            r for (cid, _), r in self._rules.items()
            if cid == event.camera_id
            and r.enabled
            and r.rule_type == target_type
            and (not r.target_geometry_id or r.target_geometry_id == event.zone_id)
            and (not r.object_classes or event.object_class.lower() in [c.lower() for c in r.object_classes])
        ]

        for rule in relevant_rules:
            cd_key = (event.camera_id, rule.rule_id, event.track_id)
            last_trig = self._cooldowns.get(cd_key, 0.0)
            if (now_mono - last_trig) < rule.cooldown_seconds:
                continue

            self._cooldowns[cd_key] = now_mono
            meta = {
                "zone_id": event.zone_id,
                "transition": event.event_type,
                "dwell_duration_ms": event.dwell_duration_ms,
            }
            matches.append(
                TriggeredRuleMatch(
                    rule=rule,
                    camera_id=event.camera_id,
                    track_id=event.track_id,
                    track_session_id=event.track_session_id,
                    geometry_id=event.zone_id,
                    object_class=event.object_class,
                    event_type=event.event_type,
                    timestamp_ns=event.timestamp_ns,
                    anchor_point=event.anchor_point,
                    metadata=meta,
                )
            )

        return matches

    def evaluate_line_event(self, event: LineCrossingEvent) -> list[TriggeredRuleMatch]:
        """Evaluate rules applicable to LINE_CROSSING events."""
        matches: list[TriggeredRuleMatch] = []
        now_mono = time.monotonic()

        relevant_rules = [
            r for (cid, _), r in self._rules.items()
            if cid == event.camera_id
            and r.enabled
            and r.rule_type == RuleType.LINE_CROSSING
            and (not r.target_geometry_id or r.target_geometry_id == event.line_id)
            and (not r.object_classes or event.object_class.lower() in [c.lower() for c in r.object_classes])
        ]

        for rule in relevant_rules:
            # Check configured direction condition if present
            req_dir = rule.conditions.get("direction", "ANY").upper()
            if req_dir != "ANY" and req_dir != event.crossing_direction:
                continue

            cd_key = (event.camera_id, rule.rule_id, event.track_id)
            last_trig = self._cooldowns.get(cd_key, 0.0)
            if (now_mono - last_trig) < rule.cooldown_seconds:
                continue

            self._cooldowns[cd_key] = now_mono
            meta = {
                "line_id": event.line_id,
                "crossing_direction": event.crossing_direction,
            }
            matches.append(
                TriggeredRuleMatch(
                    rule=rule,
                    camera_id=event.camera_id,
                    track_id=event.track_id,
                    track_session_id=event.track_session_id,
                    geometry_id=event.line_id,
                    object_class=event.object_class,
                    event_type=f"LINE_CROSSED_{event.crossing_direction}",
                    timestamp_ns=event.timestamp_ns,
                    anchor_point=event.crossing_point,
                    metadata=meta,
                )
            )

        return matches

    def evaluate_dwell_event(self, event: DwellEvent) -> list[TriggeredRuleMatch]:
        """Evaluate rules applicable to DWELL_THRESHOLD events."""
        matches: list[TriggeredRuleMatch] = []
        now_mono = time.monotonic()

        relevant_rules = [
            r for (cid, _), r in self._rules.items()
            if cid == event.camera_id
            and r.enabled
            and r.rule_type == RuleType.DWELL_THRESHOLD
            and (not r.target_geometry_id or r.target_geometry_id == event.zone_id)
            and (not r.object_classes or event.object_class.lower() in [c.lower() for c in r.object_classes])
        ]

        for rule in relevant_rules:
            # Check duration threshold
            rule_thresh_s = rule.threshold if rule.threshold > 0 else float(rule.conditions.get("minimum_duration_seconds", 0.0))
            if (event.dwell_duration_ms / 1000.0) < rule_thresh_s:
                continue

            cd_key = (event.camera_id, rule.rule_id, event.track_id)
            last_trig = self._cooldowns.get(cd_key, 0.0)
            if (now_mono - last_trig) < rule.cooldown_seconds:
                continue

            self._cooldowns[cd_key] = now_mono
            meta = {
                "zone_id": event.zone_id,
                "dwell_duration_ms": round(event.dwell_duration_ms, 1),
                "threshold_seconds": rule_thresh_s,
                "is_uncertain": event.is_uncertain,
            }
            matches.append(
                TriggeredRuleMatch(
                    rule=rule,
                    camera_id=event.camera_id,
                    track_id=event.track_id,
                    track_session_id=event.track_session_id,
                    geometry_id=event.zone_id,
                    object_class=event.object_class,
                    event_type="DWELL_THRESHOLD",
                    timestamp_ns=event.timestamp_ns,
                    anchor_point=event.anchor_point,
                    metadata=meta,
                )
            )

        return matches

    def evaluate_occupancy_threshold(
        self,
        camera_id: str,
        occupancy_type: str,  # "VISIBLE" or "FLOW"
        current_count: int,
        timestamp_ns: int,
    ) -> list[TriggeredRuleMatch]:
        """Evaluate occupancy thresholds."""
        matches: list[TriggeredRuleMatch] = []
        now_mono = time.monotonic()

        target_type = (
            RuleType.VISIBLE_OCCUPANCY_THRESHOLD
            if occupancy_type == "VISIBLE"
            else RuleType.FLOW_OCCUPANCY_THRESHOLD
        )

        relevant_rules = [
            r for (cid, _), r in self._rules.items()
            if cid == camera_id and r.enabled and r.rule_type == target_type
        ]

        for rule in relevant_rules:
            thresh = int(rule.threshold)
            if current_count < thresh:
                continue

            cd_key = (camera_id, rule.rule_id, "global")
            last_trig = self._cooldowns.get(cd_key, 0.0)
            if (now_mono - last_trig) < rule.cooldown_seconds:
                continue

            self._cooldowns[cd_key] = now_mono
            meta = {
                "occupancy_type": occupancy_type,
                "current_count": current_count,
                "threshold": thresh,
            }
            matches.append(
                TriggeredRuleMatch(
                    rule=rule,
                    camera_id=camera_id,
                    track_id="OCCUPANCY_MONITOR",
                    track_session_id="global",
                    geometry_id=rule.target_geometry_id or "camera",
                    object_class="group",
                    event_type=f"{occupancy_type}_OCCUPANCY_EXCEEDED",
                    timestamp_ns=timestamp_ns,
                    anchor_point=Point(0.5, 0.5),
                    metadata=meta,
                )
            )

        return matches
