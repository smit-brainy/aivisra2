"""Shared backend dependencies and StreamCore Engine registry.

Enables both:
1. In-process integration when StreamCore launches backend (via preview_server).
2. Standalone backend process (`python -m backend.run`) loading StreamCore on startup.
"""

import threading
from typing import Any, Optional
import os
import logging
from pathlib import Path

logger = logging.getLogger("streamcore.backend")

_ENGINE: Optional[Any] = None
_CACHE: Optional[Any] = None
_ENGINE_THREAD: Optional[threading.Thread] = None


def set_engine_and_cache(engine: Any, cache: Any = None) -> None:
    """Register active StreamCore engine and preview cache instances."""
    global _ENGINE, _CACHE
    _ENGINE = engine
    _CACHE = cache if cache is not None else getattr(engine, "preview_cache", None)


def get_engine() -> Any:
    """Retrieve the active StreamCore engine instance, initializing and starting pipeline if running standalone."""
    global _ENGINE, _CACHE, _ENGINE_THREAD
    if _ENGINE is not None:
        return _ENGINE

    # Standalone mode: initialize StreamCore from configuration
    config_path = os.environ.get("STREAMCORE_CONFIG", "runtime/streamcore/app.yaml")
    cfg_file = Path(config_path)
    if not cfg_file.is_file():
        # Fallback to default search
        candidates = [
            Path("runtime/streamcore/app.yaml"),
            Path("../runtime/streamcore/app.yaml"),
        ]
        for c in candidates:
            if c.is_file():
                cfg_file = c
                break

    try:
        from runtime.streamcore.config import load_config, load_cameras
        from runtime.streamcore.engine import StreamCore

        logger.info(f"Standalone Backend: Initializing StreamCore with {cfg_file}")
        cfg = load_config(str(cfg_file))
        cams = load_cameras(cfg_file)
        _ENGINE = StreamCore(cfg, cams)
        _CACHE = _ENGINE.preview_cache

        # In standalone backend mode, start the engine's ingestion & inference pipeline in a background daemon thread
        def _run_engine_worker():
            try:
                logger.info("Standalone Backend: Starting StreamCore video pipeline thread")
                _ENGINE.run()
            except Exception as e:
                logger.error(f"StreamCore engine background thread failed: {e}")

        _ENGINE_THREAD = threading.Thread(target=_run_engine_worker, name="streamcore-standalone-worker", daemon=True)
        _ENGINE_THREAD.start()

        return _ENGINE
    except Exception as exc:
        logger.warning(f"Could not initialize full StreamCore engine: {exc}")
        return None


def get_cache() -> Any:
    """Retrieve PreviewCache instance."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    eng = get_engine()
    if eng is not None:
        _CACHE = getattr(eng, "preview_cache", None)
    return _CACHE


def get_camera_ids() -> list[str]:
    """Return list of configured camera identifiers."""
    eng = get_engine()
    if eng is None or not getattr(eng, "cameras", None):
        return ["CAM001"]
    return [c.id for c in eng.cameras]
