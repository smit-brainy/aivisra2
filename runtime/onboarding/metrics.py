from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from threading import Lock
import time
from typing import Any


@dataclass
class OnboardingTiming:
    camera_id: str
    sample_collection_ms: float = 0.0
    scene_analysis_ms: float = 0.0
    recommendation_ms: float = 0.0
    apply_ms: float = 0.0
    total_onboarding_ms: float = 0.0
    frames_sampled: int = 0
    cpu_overhead_percent: float = 0.0
    gpu_overhead_mib: float = 0.0
    completed_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "sample_collection_ms": round(self.sample_collection_ms, 1),
            "scene_analysis_ms": round(self.scene_analysis_ms, 1),
            "recommendation_ms": round(self.recommendation_ms, 1),
            "apply_ms": round(self.apply_ms, 1),
            "total_onboarding_ms": round(self.total_onboarding_ms, 1),
            "frames_sampled": self.frames_sampled,
            "cpu_overhead_percent": round(self.cpu_overhead_percent, 1),
            "gpu_overhead_mib": round(self.gpu_overhead_mib, 1),
            "completed_at": self.completed_at,
        }


@dataclass
class AuditRecord:
    camera_id: str
    action: str  # e.g. "APPLY_CAPABILITIES", "RE_ANALYZE", "REGISTER_CAMERA"
    capabilities_before: list[str]
    capabilities_after: list[str]
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    user_or_ip: str = "127.0.0.1"
    status: str = "SUCCESS"
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "action": self.action,
            "capabilities_before": list(self.capabilities_before),
            "capabilities_after": list(self.capabilities_after),
            "timestamp": self.timestamp,
            "user_or_ip": self.user_or_ip,
            "status": self.status,
            "details": self.details,
        }


class OnboardingMetrics:
    """Records onboarding performance timings, resource overheads, and configuration audit records."""

    def __init__(self, max_audit_entries: int = 200) -> None:
        self.max_audit_entries = max_audit_entries
        self._lock = Lock()
        self._timings: dict[str, OnboardingTiming] = {}
        self._audit_log: list[AuditRecord] = []

    def record_timing(self, timing: OnboardingTiming) -> None:
        with self._lock:
            self._timings[timing.camera_id] = timing

    def get_timing(self, camera_id: str) -> OnboardingTiming | None:
        with self._lock:
            return self._timings.get(camera_id)

    def record_audit(
        self,
        camera_id: str,
        action: str,
        capabilities_before: list[str],
        capabilities_after: list[str],
        user_or_ip: str = "127.0.0.1",
        status: str = "SUCCESS",
        details: str = "",
    ) -> AuditRecord:
        record = AuditRecord(
            camera_id=camera_id,
            action=action,
            capabilities_before=list(capabilities_before),
            capabilities_after=list(capabilities_after),
            user_or_ip=user_or_ip,
            status=status,
            details=details,
        )
        with self._lock:
            self._audit_log.append(record)
            if len(self._audit_log) > self.max_audit_entries:
                self._audit_log = self._audit_log[-self.max_audit_entries:]
        return record

    def get_audit_log(self, camera_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            records = self._audit_log
            if camera_id is not None:
                records = [r for r in records if r.camera_id == camera_id]
            return [r.to_dict() for r in records[-limit:]]

