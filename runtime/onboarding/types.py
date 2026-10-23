from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import time
from typing import Any
import numpy as np


class OnboardingStatus(StrEnum):
    CONNECTED = "CONNECTED"
    SAMPLING = "SAMPLING"
    ANALYZING = "ANALYZING"
    RECOMMENDATIONS_READY = "RECOMMENDATIONS_READY"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    USER_APPLIES = "USER_APPLIES"
    VALIDATING = "VALIDATING"
    ACTIVATING = "ACTIVATING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"


class ImplementationStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    REQUIRES_SETUP = "REQUIRES_SETUP"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    UNAVAILABLE = "UNAVAILABLE"


class SceneType(StrEnum):
    ENTRANCE = "entrance"
    PARKING = "parking"
    ROAD = "road"
    FACTORY = "factory"
    WAREHOUSE = "warehouse"
    RETAIL = "retail"
    OFFICE = "office"
    OUTDOOR = "outdoor"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class FrameSample:
    camera_id: str
    sequence: int
    timestamp: float
    image_bgr: np.ndarray
    width: int
    height: int


@dataclass(slots=True)
class SceneProfile:
    camera_id: str
    scene_type: str
    scene_confidence: float
    frames_analyzed: int
    objects: list[str] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    analysis_method: str = "yolo_heuristic"
    limitations: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "scene_type": self.scene_type,
            "scene_confidence": round(self.scene_confidence, 2),
            "frames_analyzed": self.frames_analyzed,
            "objects": list(self.objects),
            "attributes": list(self.attributes),
            "analysis_method": self.analysis_method,
            "limitations": list(self.limitations),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    id: str
    display_name: str
    description: str
    category: str
    dependencies: tuple[str, ...] = ()
    required_models: tuple[str, ...] = ()
    implementation_status: ImplementationStatus = ImplementationStatus.AVAILABLE
    requires_configuration: tuple[str, ...] = ()
    supported_classes: tuple[str, ...] = ()
    estimated_compute_cost: str = "Low"  # Low, Medium, High
    default_enabled: bool = False
    runtime_component: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "dependencies": list(self.dependencies),
            "required_models": list(self.required_models),
            "implementation_status": str(self.implementation_status),
            "requires_configuration": list(self.requires_configuration),
            "supported_classes": list(self.supported_classes),
            "estimated_compute_cost": self.estimated_compute_cost,
            "default_enabled": self.default_enabled,
            "runtime_component": self.runtime_component,
        }


@dataclass(slots=True)
class CapabilityRecommendation:
    capability_id: str
    display_name: str
    score: float
    reason: str
    evidence: list[str] = field(default_factory=list)
    available: bool = True
    recommended_checked: bool = False
    status: str = "AVAILABLE"
    dependencies: list[str] = field(default_factory=list)
    requires_configuration: list[str] = field(default_factory=list)
    estimated_compute_cost: str = "Low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "display_name": self.display_name,
            "score": round(self.score, 2),
            "reason": self.reason,
            "evidence": list(self.evidence),
            "available": self.available,
            "recommended_checked": self.recommended_checked,
            "status": self.status,
            "dependencies": list(self.dependencies),
            "requires_configuration": list(self.requires_configuration),
            "estimated_compute_cost": self.estimated_compute_cost,
        }


@dataclass(slots=True)
class CameraCapabilityConfig:
    camera_id: str
    version: int
    enabled_capabilities: list[str]
    updated_at: str
    status: str = "ACTIVE"
    configurations: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "version": self.version,
            "enabled_capabilities": list(self.enabled_capabilities),
            "updated_at": self.updated_at,
            "status": self.status,
            "configurations": dict(self.configurations),
        }


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    resolved_capabilities: list[str] = field(default_factory=list)
    required_models: list[str] = field(default_factory=list)
    required_runtime_components: list[str] = field(default_factory=list)
    missing_dependencies: dict[str, list[str]] = field(default_factory=dict)
    unsupported_capabilities: list[str] = field(default_factory=list)
    missing_configuration: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "resolved_capabilities": list(self.resolved_capabilities),
            "required_models": list(self.required_models),
            "required_runtime_components": list(self.required_runtime_components),
            "missing_dependencies": self.missing_dependencies,
            "unsupported_capabilities": list(self.unsupported_capabilities),
            "missing_configuration": self.missing_configuration,
            "errors": list(self.errors),
        }
