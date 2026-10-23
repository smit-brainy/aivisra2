"""AIVISRA Smart Camera Onboarding & AI Capability Recommendation Subsystem."""

from .types import (
    OnboardingStatus,
    ImplementationStatus,
    SceneType,
    FrameSample,
    SceneProfile,
    CapabilityDefinition,
    CapabilityRecommendation,
    CameraCapabilityConfig,
    ValidationResult,
)
from .frame_sampler import FrameSampler
from .scene_profiler import SceneProfiler
from .capability_registry import CapabilityRegistry
from .capability_recommender import CapabilityRecommender
from .capability_resolver import CapabilityResolver
from .capability_manager import CapabilityManager
from .camera_config_store import CameraConfigStore
from .onboarding_service import OnboardingService, sanitize_rtsp_url
from .metrics import OnboardingMetrics, OnboardingTiming, AuditRecord

__all__ = [
    "OnboardingStatus",
    "ImplementationStatus",
    "SceneType",
    "FrameSample",
    "SceneProfile",
    "CapabilityDefinition",
    "CapabilityRecommendation",
    "CameraCapabilityConfig",
    "ValidationResult",
    "FrameSampler",
    "SceneProfiler",
    "CapabilityRegistry",
    "CapabilityRecommender",
    "CapabilityResolver",
    "CapabilityManager",
    "CameraConfigStore",
    "OnboardingService",
    "sanitize_rtsp_url",
    "OnboardingMetrics",
    "OnboardingTiming",
    "AuditRecord",
]

