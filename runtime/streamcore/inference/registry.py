"""Plug-and-play detector registry and dynamic model loader for StreamCore."""

import importlib
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Type

from ..config import InferenceConfig
from .base import Detector

logger = logging.getLogger(__name__)

# Global detector registry mapping: identifier -> detector class
_DETECTOR_REGISTRY: dict[str, Type[Detector]] = {}


def register_detector(*names: str) -> Callable[[Type[Detector]], Type[Detector]]:
    """Decorator to register a detector class under one or more alias names."""
    def decorator(cls: Type[Detector]) -> Type[Detector]:
        if not issubclass(cls, Detector):
            raise TypeError(f"Class {cls.__name__} must inherit from Detector")
        for name in names:
            key = name.strip().lower()
            _DETECTOR_REGISTRY[key] = cls
            logger.debug("Registered detector: %s -> %s", key, cls.__name__)
        return cls
    return decorator


def list_registered_detectors() -> list[str]:
    """Return sorted list of all registered detector names."""
    return sorted(_DETECTOR_REGISTRY.keys())


def load_detector_from_file(file_path: str | Path, class_name: str | None = None) -> Type[Detector]:
    """Dynamically load a Detector class from an external Python script."""
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Custom detector file not found: {p}")

    module_name = f"custom_detector_{p.stem}"
    spec = importlib.util.spec_from_file_location(module_name, str(p))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module spec from {p}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if class_name:
        cls = getattr(module, class_name, None)
        if cls is None or not inspect.isclass(cls) or not issubclass(cls, Detector):
            raise TypeError(f"Class {class_name} not found or not a Detector subclass in {p}")
        return cls

    # Auto-discover first subclass of Detector in module
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if inspect.isclass(attr) and issubclass(attr, Detector) and attr is not Detector:
            return attr

    raise TypeError(f"No Detector subclass found in {p}")


def load_detector_from_classpath(classpath: str) -> Type[Detector]:
    """Dynamically load a Detector class from module path (e.g. 'pkg.mod:MyClass')."""
    if ":" in classpath:
        mod_name, cls_name = classpath.split(":", 1)
    else:
        parts = classpath.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid classpath format: {classpath}")
        mod_name, cls_name = parts

    module = importlib.import_module(mod_name)
    cls = getattr(module, cls_name)
    if not issubclass(cls, Detector):
        raise TypeError(f"{classpath} is not a subclass of Detector")
    return cls


def create_detector(config: InferenceConfig) -> Detector | None:
    """
    Factory function to instantiate the configured detector.
    Supports:
    1. Built-in detectors: 'none', 'dummy', 'ultralytics', 'yolo'
    2. Any registered detector plugin
    3. Custom file path via config.custom_detector_file
    4. Custom classpath via config.custom_detector_class
    """
    name = (config.detector or "ultralytics").strip().lower()

    if name == "none":
        return None

    # Check for external custom file override
    custom_file = getattr(config, "custom_detector_file", None)
    if custom_file:
        cls = load_detector_from_file(custom_file)
        return cls(config)

    # Check for external classpath override
    custom_classpath = getattr(config, "custom_detector_class", None)
    if custom_classpath:
        cls = load_detector_from_classpath(custom_classpath)
        return cls(config)

    # Lazily register built-in detectors if not yet loaded
    if "dummy" not in _DETECTOR_REGISTRY:
        from .dummy import DummyDetector
        register_detector("dummy")(DummyDetector)

    if "ultralytics" not in _DETECTOR_REGISTRY:
        from .ultralytics_detector import UltralyticsDetector
        register_detector("ultralytics", "yolo", "yolo11", "yolov8", "rtdetr")(UltralyticsDetector)

    if name in _DETECTOR_REGISTRY:
        detector_cls = _DETECTOR_REGISTRY[name]
        try:
            return detector_cls(config)
        except TypeError:
            return detector_cls()

    # Attempt dynamic import if user passed 'mymodule.MyDetector'
    if "." in name:
        try:
            cls = load_detector_from_classpath(name)
            try:
                return cls(config)
            except TypeError:
                return cls()
        except Exception as exc:
            raise ValueError(f"Failed to load detector class '{name}': {exc}") from exc

    available = ", ".join(list_registered_detectors())
    raise ValueError(f"Unknown detector '{name}'. Registered options: {available}")
