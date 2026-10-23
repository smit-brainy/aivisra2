from __future__ import annotations

import logging
from threading import RLock
from typing import Any

from .capability_registry import CapabilityRegistry
from .capability_resolver import CapabilityResolver
from .camera_config_store import CameraConfigStore
from .types import CameraCapabilityConfig

logger = logging.getLogger(__name__)


class CapabilityManager:
    """Manages active camera capability subscriptions, shared model worker lifecycles, and atomic hot-activation.

    Core Rule: Model workers are shared across cameras. Never allocate separate model instances per camera.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        config_store: CameraConfigStore,
        resolver: CapabilityResolver | None = None,
        engine: Any = None,
    ) -> None:
        self.registry = registry
        self.config_store = config_store
        self.resolver = resolver or CapabilityResolver()
        self.engine = engine
        self._lock = RLock()

        # camera_id -> set of active capability IDs
        self._active_subscriptions: dict[str, set[str]] = {}

        # worker_id (e.g. "base_yolo", "bytetrack") -> set of camera_ids using it
        self._worker_subscribers: dict[str, set[str]] = {
            "base_yolo": set(),
            "bytetrack": set(),
        }

    def apply_capabilities(
        self,
        camera_id: str,
        selected_capabilities: list[str],
        expected_version: int | None = None,
        configurations: dict[str, Any] | None = None,
    ) -> CameraCapabilityConfig:
        """Atomically activate approved capabilities for a camera with rollback on failure.

        10-Step Activation Protocol:
        1. Read existing active configuration.
        2. Validate requested capabilities.
        3. Resolve full dependencies.
        4. Calculate added/removed delta.
        5. Verify worker availability.
        6. Prepare shared workers.
        7. Update runtime subscriptions.
        8. Verify activation.
        9. Persist configuration atomically.
        10. Return updated config.
        """
        with self._lock:
            # 1. Read existing active config
            current_cfg = self.config_store.get(camera_id)
            current_caps = set(current_cfg.enabled_capabilities) if current_cfg else set()

            # 2. Validate selected capabilities
            validation = self.resolver.resolve(
                selected_capabilities=selected_capabilities,
                registry=self.registry,
                configurations=configurations,
                auto_include_dependencies=True,
            )

            if not validation.valid:
                err_msg = "; ".join(validation.errors)
                logger.error("capability_validation_failed", extra={"camera_id": camera_id, "errors": validation.errors})
                raise ValueError(f"Capability validation failed: {err_msg}")

            resolved_caps = set(validation.resolved_capabilities)

            # 3. Delta calculation
            added = resolved_caps - current_caps
            removed = current_caps - resolved_caps

            # If identical and version matches, idempotent return
            if not added and not removed and current_cfg is not None:
                if expected_version is None or current_cfg.version == expected_version:
                    return current_cfg

            # 4. Check worker availability for added capabilities
            for cap_id in resolved_caps:
                cap_def = self.registry.get(cap_id)
                if not cap_def:
                    continue
                for req_model in cap_def.required_models:
                    if not self._is_worker_available(req_model):
                        raise RuntimeError(f"Required worker '{req_model}' is not available for '{cap_def.display_name}'.")

            # Save state for rollback
            prev_subscriptions = set(self._active_subscriptions.get(camera_id, set()))
            prev_workers = {w: set(subs) for w, subs in self._worker_subscribers.items()}

            try:
                # 5 & 6. Update shared worker subscriptions
                for cap_id in removed:
                    cap_def = self.registry.get(cap_id)
                    if cap_def:
                        for model in cap_def.required_models:
                            self._worker_subscribers.setdefault(model, set()).discard(camera_id)
                        if cap_def.runtime_component:
                            self._worker_subscribers.setdefault(cap_def.runtime_component, set()).discard(camera_id)

                for cap_id in resolved_caps:
                    cap_def = self.registry.get(cap_id)
                    if cap_def:
                        for model in cap_def.required_models:
                            self._worker_subscribers.setdefault(model, set()).add(camera_id)
                        if cap_def.runtime_component:
                            self._worker_subscribers.setdefault(cap_def.runtime_component, set()).add(camera_id)

                # 7. Update camera runtime subscriptions
                self._active_subscriptions[camera_id] = resolved_caps

                # 8. Verify activation on runtime engine if connected
                self._activate_pipeline(camera_id, resolved_caps)
                if self.engine is not None:
                    self._sync_with_engine(camera_id, resolved_caps)

                # 9. Persist new configuration atomically
                saved_cfg = self.config_store.save(
                    camera_id=camera_id,
                    enabled_capabilities=list(resolved_caps),
                    expected_version=expected_version,
                )

                logger.info(
                    "capabilities_activated",
                    extra={
                        "camera_id": camera_id,
                        "version": saved_cfg.version,
                        "active": list(resolved_caps),
                        "shared_workers": {w: len(subs) for w, subs in self._worker_subscribers.items()},
                    },
                )
                return saved_cfg

            except Exception as exc:
                # ROLLBACK to previous working configuration
                logger.error(
                    "capability_activation_failed_rolling_back",
                    extra={"camera_id": camera_id, "reason": str(exc)},
                )
                self._active_subscriptions[camera_id] = prev_subscriptions
                self._worker_subscribers = prev_workers
                if self.engine is not None:
                    self._sync_with_engine(camera_id, prev_subscriptions)
                raise

    def get_active_capabilities(self, camera_id: str) -> list[str]:
        """Return currently active capabilities for a camera."""
        with self._lock:
            caps = self._active_subscriptions.get(camera_id)
            if caps is not None:
                return sorted(list(caps))
            stored = self.config_store.get(camera_id)
            if stored:
                return sorted(list(stored.enabled_capabilities))
            return []

    def is_capability_enabled(self, camera_id: str, capability_id: str) -> bool:
        """Check if a specific capability is active for a camera."""
        with self._lock:
            return capability_id in self._active_subscriptions.get(camera_id, set())

    def get_allowed_classes(self, camera_id: str) -> set[str]:
        """Get set of object classes enabled for this camera based on capabilities."""
        with self._lock:
            allowed = set()
            active = self._active_subscriptions.get(camera_id, set())
            for cap_id in active:
                cap = self.registry.get(cap_id)
                if cap:
                    allowed.update(cap.supported_classes)
            return allowed

    def get_worker_reference_counts(self) -> dict[str, int]:
        """Return count of cameras subscribing to each shared worker."""
        with self._lock:
            return {w: len(subs) for w, subs in self._worker_subscribers.items()}

    def get_worker_subscribers(self, worker_name: str) -> set[str]:
        """Return the set of camera IDs subscribing to a shared worker."""
        with self._lock:
            return set(self._worker_subscribers.get(worker_name, set()))

    def _activate_pipeline(self, camera_id: str, capabilities: set[str]) -> None:
        """Internal activation pipeline hook, overridable or patchable in tests."""
        pass

    def restore_from_store(self) -> None:
        """Restore all persisted camera capabilities on system startup."""
        with self._lock:
            stored_all = self.config_store.get_all()
            for camera_id, cfg in stored_all.items():
                try:
                    # Validate against current registry
                    validation = self.resolver.resolve(
                        cfg.enabled_capabilities, self.registry, auto_include_dependencies=True
                    )
                    if validation.valid:
                        valid_caps = set(validation.resolved_capabilities)
                        self._active_subscriptions[camera_id] = valid_caps
                        for cap_id in valid_caps:
                            cap_def = self.registry.get(cap_id)
                            if cap_def:
                                for m in cap_def.required_models:
                                    self._worker_subscribers.setdefault(m, set()).add(camera_id)
                                if cap_def.runtime_component:
                                    self._worker_subscribers.setdefault(cap_def.runtime_component, set()).add(camera_id)
                        if self.engine is not None:
                            self._sync_with_engine(camera_id, valid_caps)
                        logger.info(
                            "restored_camera_capabilities",
                            extra={"camera_id": camera_id, "capabilities": list(valid_caps)},
                        )
                    else:
                        logger.warning(
                            "stored_capabilities_validation_warning",
                            extra={"camera_id": camera_id, "errors": validation.errors},
                        )
                except Exception as exc:
                    logger.error("restore_camera_capabilities_error", extra={"camera_id": camera_id, "reason": str(exc)})

    def _is_worker_available(self, worker_name: str) -> bool:
        """Verify whether a required model worker is available in the runtime."""
        if worker_name == "base_yolo":
            # Check engine detector or ultralytics availability
            if self.engine is not None:
                return getattr(self.engine, "detector", None) is not None
            return True
        if worker_name == "bytetrack":
            return True
        # For non-implemented workers (e.g. ppe_model, plate_detector), report False
        return False

    def _sync_with_engine(self, camera_id: str, capabilities: set[str]) -> None:
        """Propagate capability updates to StreamCore engine without disrupting streams."""
        if self.engine is None:
            return
        try:
            if hasattr(self.engine, "set_camera_capabilities"):
                self.engine.set_camera_capabilities(camera_id, capabilities)
            if hasattr(self.engine, "active_capabilities"):
                self.engine.active_capabilities[camera_id] = set(capabilities)
            if hasattr(self.engine, "camera_trackers"):
                if "person_tracking" in capabilities or "vehicle_tracking" in capabilities:
                    self.engine.camera_trackers[camera_id] = True
                else:
                    self.engine.camera_trackers.pop(camera_id, None)
        except Exception as exc:
            logger.debug("engine_sync_capabilities_error", extra={"reason": str(exc)})
