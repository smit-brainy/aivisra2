from __future__ import annotations

import logging
import re
from threading import Lock, Semaphore, Thread
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .capability_manager import CapabilityManager
from .capability_recommender import CapabilityRecommender
from .capability_registry import CapabilityRegistry
from .capability_resolver import CapabilityResolver
from .camera_config_store import CameraConfigStore
from .frame_sampler import FrameSampler
from .metrics import OnboardingMetrics, OnboardingTiming
from .scene_profiler import SceneProfiler
from .types import (
    CapabilityRecommendation,
    OnboardingStatus,
    SceneProfile,
)

logger = logging.getLogger(__name__)


def sanitize_rtsp_url(url: str) -> str:
    """Sanitize RTSP URL by redacting credentials so passwords are never exposed."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        if parts.password is not None and parts.username is not None:
            netloc = f"{parts.username}:***@{parts.hostname}"
            if parts.port:
                netloc += f":{parts.port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass
    # Regex fallback
    return re.sub(r":([^:@]+)@", r":***@", url)


class OnboardingService:
    """Coordinates camera registration, frame sampling, scene profiling, capability recommendation, and approval-gated activation."""

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        config_store: CameraConfigStore | None = None,
        engine: Any = None,
        detector: Any = None,
        max_concurrent_profiling: int = 2,
    ) -> None:
        self.registry = registry or CapabilityRegistry()
        self.config_store = config_store or CameraConfigStore()
        self.engine = engine
        self.resolver = CapabilityResolver()
        self.recommender = CapabilityRecommender()
        self.sampler = FrameSampler(sample_count=20, sample_duration_seconds=8.0)
        self.profiler = SceneProfiler(detector=detector or getattr(engine, "detector", None))
        self.capability_manager = CapabilityManager(
            registry=self.registry,
            config_store=self.config_store,
            resolver=self.resolver,
            engine=self.engine,
        )
        self.metrics = OnboardingMetrics()

        self._profiling_semaphore = Semaphore(max_concurrent_profiling)
        self._lock = Lock()

        # camera_id -> state dict
        self._camera_states: dict[str, dict[str, Any]] = {}
        # camera_id -> SceneProfile
        self._scene_profiles: dict[str, SceneProfile] = {}
        # camera_id -> list[CapabilityRecommendation]
        self._draft_recommendations: dict[str, list[CapabilityRecommendation]] = {}

        # Restore stored configurations
        self.capability_manager.restore_from_store()

    def register_camera(
        self,
        camera_id: str,
        rtsp_uri: str,
        codec: str = "h264",
        decoder: str = "auto",
        live_path: str | None = None,
    ) -> dict[str, Any]:
        """Validate and register a new camera for onboarding.

        - Validates unique camera ID.
        - Validates URI format and sanitizes credentials.
        - Integrates with running StreamCore engine if present.
        """
        cid = camera_id.strip()
        if not cid or not re.match(r"^[A-Za-z0-9_-]+$", cid):
            raise ValueError("Invalid camera ID: Must be non-empty alphanumeric with hyphens or underscores.")

        with self._lock:
            # Check uniqueness against runtime engine and stored configs
            existing_cams = [c.id for c in getattr(self.engine, "cameras", [])] if self.engine else []
            if cid in existing_cams or cid in self._camera_states:
                raise ValueError(f"Camera ID '{cid}' already exists. Choose a unique camera name.")

            sanitized_uri = sanitize_rtsp_url(rtsp_uri)
            parts = urlsplit(rtsp_uri)
            if parts.scheme not in ("rtsp", "rtsps", "file", "videotestsrc"):
                raise ValueError(f"Unsupported URI scheme '{parts.scheme}'. Expected rtsp:// or rtsps://.")

            # Register camera in engine if running
            if self.engine is not None and hasattr(self.engine, "register_camera"):
                try:
                    self.engine.register_camera(cid, rtsp_uri, codec=codec, decoder=decoder, live_path=live_path or cid.lower())
                except Exception as exc:
                    logger.error("engine_camera_registration_failed", extra={"camera_id": cid, "reason": str(exc)})
                    raise RuntimeError(f"Failed to connect camera stream: {str(exc)}")

            self._camera_states[cid] = {
                "status": OnboardingStatus.CONNECTED,
                "camera_id": cid,
                "sanitized_uri": sanitized_uri,
                "codec": codec,
                "decoder": decoder,
                "sample_count": 0,
                "target_samples": 20,
                "progress_percent": 0,
                "error": None,
                "registered_at": time.time(),
            }

            self.metrics.record_audit(
                camera_id=cid,
                action="REGISTER_CAMERA",
                capabilities_before=[],
                capabilities_after=[],
                details=f"Registered stream {sanitized_uri}",
            )

            logger.info("camera_registered_for_onboarding", extra={"camera_id": cid, "uri": sanitized_uri})
            return {
                "camera_id": cid,
                "status": OnboardingStatus.CONNECTED,
                "sanitized_uri": sanitized_uri,
                "registered_at": self._camera_states[cid]["registered_at"],
            }

    def start_analysis(
        self,
        camera_id: str,
        sample_count: int = 20,
        sample_duration_seconds: float = 8.0,
        force_fresh: bool = False,
    ) -> dict[str, Any]:
        """Trigger asynchronous scene profiling and capability recommendation."""
        with self._lock:
            state = self._camera_states.get(camera_id)
            if not state:
                # If camera exists in engine, auto-initialize state
                existing_cams = [c.id for c in getattr(self.engine, "cameras", [])] if self.engine else []
                if camera_id in existing_cams:
                    state = {
                        "status": OnboardingStatus.CONNECTED,
                        "camera_id": camera_id,
                        "sample_count": 0,
                        "target_samples": sample_count,
                        "progress_percent": 0,
                        "error": None,
                        "registered_at": time.time(),
                    }
                    self._camera_states[camera_id] = state
                else:
                    raise ValueError(f"Camera '{camera_id}' is not registered.")

            if state["status"] in (OnboardingStatus.SAMPLING, OnboardingStatus.ANALYZING) and not force_fresh:
                return {
                    "camera_id": camera_id,
                    "status": state["status"],
                    "message": "Analysis is already in progress.",
                }

            state["status"] = OnboardingStatus.SAMPLING
            state["sample_count"] = 0
            state["target_samples"] = sample_count
            state["progress_percent"] = 5
            state["error"] = None

        thread = Thread(
            target=self._run_analysis_job,
            args=(camera_id, sample_count, sample_duration_seconds),
            name=f"onboarding-analysis-{camera_id}",
            daemon=True,
        )
        thread.start()

        return {
            "camera_id": camera_id,
            "status": OnboardingStatus.SAMPLING,
            "message": "Analysis started in background.",
        }

    def get_status(self, camera_id: str) -> dict[str, Any]:
        """Get current onboarding lifecycle status and sampling progress."""
        with self._lock:
            state = self._camera_states.get(camera_id)
            if not state:
                active_caps = self.capability_manager.get_active_capabilities(camera_id)
                if active_caps:
                    return {
                        "camera_id": camera_id,
                        "status": OnboardingStatus.ACTIVE,
                        "sample_count": 20,
                        "error": None,
                    }
                raise ValueError(f"Camera '{camera_id}' not found.")

            return {
                "camera_id": camera_id,
                "status": state["status"],
                "sample_count": state.get("sample_count", 0),
                "target_samples": state.get("target_samples", 20),
                "progress_percent": state.get("progress_percent", 0),
                "error": state.get("error"),
            }

    def get_recommendations(self, camera_id: str) -> dict[str, Any]:
        """Return scene profile, ranked recommendations, and comparison against active configuration."""
        with self._lock:
            profile = self._scene_profiles.get(camera_id)
            recs = self._draft_recommendations.get(camera_id, [])
            active_caps = self.capability_manager.get_active_capabilities(camera_id)

            if profile is None and not recs:
                # If not analyzed yet, return fallback with default registry recommendations
                recs = [
                    CapabilityRecommendation(
                        capability_id=c.id,
                        display_name=c.display_name,
                        score=0.50 if c.id in ("person_detection", "person_tracking") else 0.20,
                        reason="Standard capability definition.",
                        available=c.implementation_status != "NOT_IMPLEMENTED",
                        recommended_checked=c.default_enabled,
                        status=str(c.implementation_status),
                        dependencies=list(c.dependencies),
                        requires_configuration=list(c.requires_configuration),
                        estimated_compute_cost=c.estimated_compute_cost,
                    )
                    for c in self.registry.all()
                ]

            # Build comparison of active vs recommended
            rec_map = {r.capability_id: r for r in recs}
            comparison = []
            for c in self.registry.all():
                is_active = c.id in active_caps
                r = rec_map.get(c.id)
                rec_checked = r.recommended_checked if r else False
                score = r.score if r else 0.0
                comparison.append({
                    "id": c.id,
                    "display_name": c.display_name,
                    "active": is_active,
                    "recommended": rec_checked,
                    "score": score,
                    "status": str(c.implementation_status),
                })

            current_status = self._camera_states.get(camera_id, {}).get("status", OnboardingStatus.ACTIVE if active_caps else OnboardingStatus.CONNECTED)

            return {
                "camera_id": camera_id,
                "status": current_status,
                "scene_profile": profile.to_dict() if profile else None,
                "recommendations": [r.to_dict() for r in recs],
                "active_capabilities": active_caps,
                "comparison": comparison,
            }

    def apply_capabilities(
        self,
        camera_id: str,
        selected_capabilities: list[str],
        expected_config_version: int | None = None,
        configurations: dict[str, Any] | None = None,
        user_ip: str = "127.0.0.1",
    ) -> dict[str, Any]:
        """Apply and activate user-approved capabilities following the strict 10-step protocol."""
        with self._lock:
            state = self._camera_states.setdefault(camera_id, {
                "camera_id": camera_id,
                "status": OnboardingStatus.USER_APPLIES,
            })
            state["status"] = OnboardingStatus.VALIDATING

        t_start = time.monotonic()
        caps_before = self.capability_manager.get_active_capabilities(camera_id)

        try:
            with self._lock:
                state["status"] = OnboardingStatus.ACTIVATING

            cfg = self.capability_manager.apply_capabilities(
                camera_id=camera_id,
                selected_capabilities=selected_capabilities,
                expected_version=expected_config_version,
                configurations=configurations,
            )

            with self._lock:
                state["status"] = OnboardingStatus.ACTIVE

            apply_ms = (time.monotonic() - t_start) * 1000.0
            timing = self.metrics.get_timing(camera_id)
            if timing:
                timing.apply_ms = apply_ms
                timing.total_onboarding_ms += apply_ms

            self.metrics.record_audit(
                camera_id=camera_id,
                action="APPLY_CAPABILITIES",
                capabilities_before=caps_before,
                capabilities_after=cfg.enabled_capabilities,
                user_or_ip=user_ip,
                status="SUCCESS",
            )

            return {
                "camera_id": camera_id,
                "status": OnboardingStatus.ACTIVE,
                "config_version": cfg.version,
                "enabled_capabilities": cfg.enabled_capabilities,
                "updated_at": cfg.updated_at,
            }

        except Exception as exc:
            with self._lock:
                state["status"] = OnboardingStatus.WAITING_FOR_USER
                state["error"] = str(exc)

            self.metrics.record_audit(
                camera_id=camera_id,
                action="APPLY_CAPABILITIES",
                capabilities_before=caps_before,
                capabilities_after=[],
                user_or_ip=user_ip,
                status="FAILED",
                details=str(exc),
            )
            raise

    def _run_analysis_job(self, camera_id: str, sample_count: int, sample_duration: float) -> None:
        """Background worker executing bounded frame sampling and scene profiling."""
        with self._profiling_semaphore:
            t0 = time.monotonic()
            timing = OnboardingTiming(camera_id=camera_id)
            try:
                # 1. SAMPLING PHASE
                with self._lock:
                    if camera_id in self._camera_states:
                        self._camera_states[camera_id]["status"] = OnboardingStatus.SAMPLING

                def progress_cb(collected: int, target: int) -> None:
                    with self._lock:
                        if camera_id in self._camera_states:
                            pct = int(10 + (collected / float(target)) * 50)
                            self._camera_states[camera_id]["sample_count"] = collected
                            self._camera_states[camera_id]["progress_percent"] = min(60, pct)

                def get_frame(cid: str) -> Any:
                    if self.engine is not None and hasattr(self.engine, "store"):
                        return self.engine.store.latest(cid)
                    return None

                sampler = FrameSampler(sample_count=sample_count, sample_duration_seconds=sample_duration)
                samples = sampler.sample_from_store(
                    camera_id=camera_id,
                    get_latest_frame_fn=get_frame,
                    progress_callback=progress_cb,
                )

                timing.sample_collection_ms = (time.monotonic() - t0) * 1000.0
                timing.frames_sampled = len(samples)

                # 2. ANALYZING PHASE
                t_prof = time.monotonic()
                with self._lock:
                    if camera_id in self._camera_states:
                        self._camera_states[camera_id]["status"] = OnboardingStatus.ANALYZING
                        self._camera_states[camera_id]["progress_percent"] = 75

                profile = self.profiler.analyze(samples, camera_id=camera_id)
                timing.scene_analysis_ms = (time.monotonic() - t_prof) * 1000.0

                # 3. RECOMMENDATIONS PHASE
                t_rec = time.monotonic()
                recs = self.recommender.recommend(profile, self.registry)
                timing.recommendation_ms = (time.monotonic() - t_rec) * 1000.0
                timing.total_onboarding_ms = (time.monotonic() - t0) * 1000.0

                with self._lock:
                    self._scene_profiles[camera_id] = profile
                    self._draft_recommendations[camera_id] = recs
                    if camera_id in self._camera_states:
                        self._camera_states[camera_id]["status"] = OnboardingStatus.RECOMMENDATIONS_READY
                        self._camera_states[camera_id]["progress_percent"] = 100
                        self._camera_states[camera_id]["sample_count"] = len(samples)

                self.metrics.record_timing(timing)
                logger.info(
                    "onboarding_analysis_completed",
                    extra={
                        "camera_id": camera_id,
                        "scene_type": profile.scene_type,
                        "samples": len(samples),
                        "total_ms": timing.total_onboarding_ms,
                    },
                )

                # Transition to WAITING_FOR_USER
                with self._lock:
                    if camera_id in self._camera_states:
                        self._camera_states[camera_id]["status"] = OnboardingStatus.WAITING_FOR_USER

            except Exception as exc:
                logger.error("onboarding_analysis_failed", extra={"camera_id": camera_id, "reason": str(exc)})
                with self._lock:
                    if camera_id in self._camera_states:
                        self._camera_states[camera_id]["status"] = OnboardingStatus.FAILED
                        self._camera_states[camera_id]["error"] = str(exc)

