"""
Example Custom Plug-and-Play Detector Plugin for StreamCore.
============================================================
This demonstrates how to create a custom detector (e.g. for ONNX Runtime, TensorRT,
RF-DETR, YOLOv10, or custom PyTorch models) without changing any StreamCore engine code.

How to use:
-----------
Method 1 (Registry Plugin):
    Import this file anywhere, or register with:
    from mis.runtime.streamcore.inference import register_detector
    @register_detector("my_custom_model")
    class MyCustomDetector(Detector): ...

    In app.yaml:
    inference:
      detector: "my_custom_model"

Method 2 (External File Path):
    In app.yaml:
    inference:
      custom_detector_file: "path/to/example_custom_detector.py"
"""

import logging
from time import monotonic, time
from typing import Any

import numpy as np

from ..config import InferenceConfig
from ..types import CameraFrame, Detection, DetectionResult, InferenceBatch
from .base import Detector
from .registry import register_detector

logger = logging.getLogger(__name__)


@register_detector("example_custom", "custom_template")
class ExampleCustomDetector(Detector):
    """
    Template plug-and-play detector plugin.
    Implements the standard 4-method contract: load, warmup, infer, close.
    """

    def __init__(self, config: InferenceConfig) -> None:
        self.config = config
        self._model: Any = None
        logger.info("Initialized ExampleCustomDetector for model: %s", config.model_path)

    def load(self) -> None:
        """Load model weights (e.g. PyTorch .pt, ONNX .onnx, or TensorRT .engine)."""
        logger.info("Loading custom model from %s...", self.config.model_path)
        # e.g.:
        # self._model = onnxruntime.InferenceSession(self.config.model_path)
        # or self._model = torch.load(...)
        self._model = "loaded"

    def warmup(self) -> None:
        """Run a single dummy warmup inference pass."""
        dummy_frame = CameraFrame(
            camera_id="warmup",
            sequence=0,
            timestamp=time(),
            received_monotonic=monotonic(),
            image=np.zeros((self.config.imgsz, self.config.imgsz, 3), dtype=np.uint8),
            width=self.config.imgsz,
            height=self.config.imgsz,
        )
        self.infer([dummy_frame])
        logger.info("ExampleCustomDetector warmup complete.")

    def infer(self, batch: list[CameraFrame] | InferenceBatch) -> list[DetectionResult]:
        """
        Run inference on the batch and return DetectionResult objects.
        Supports both:
        - InferenceBatch (zero-copy CUDA tensor directly on GPU)
        - list[CameraFrame] (CPU NumPy arrays)
        """
        started = monotonic()

        if isinstance(batch, InferenceBatch):
            frames = batch.frames
            count = batch.batch_size
        else:
            frames = batch
            count = len(batch)

        results: list[DetectionResult] = []
        finished = monotonic()
        inference_ms = (finished - started) * 1000.0

        for frame in frames:
            # Example: produce detections formatted as Detection(...)
            # class_id, label, confidence, norm_x1, norm_y1, norm_x2, norm_y2 (0.0 to 1.0)
            detections = [
                Detection(
                    class_id=0,
                    label="person",
                    confidence=0.92,
                    x1=0.2,
                    y1=0.2,
                    x2=0.5,
                    y2=0.8,
                )
            ]
            cam_id = getattr(frame, "camera_id", "cam")
            seq = getattr(frame, "sequence", 0)
            ts = getattr(frame, "timestamp", time())
            w = getattr(frame, "width", 1280)
            h = getattr(frame, "height", 720)
            rec = getattr(frame, "received_monotonic", started)

            results.append(
                DetectionResult(
                    camera_id=cam_id,
                    frame_sequence=seq,
                    timestamp=ts,
                    detections=detections,
                    inference_ms=inference_ms,
                    total_latency_ms=max(0.0, (finished - rec) * 1000.0),
                    source_width=w,
                    source_height=h,
                )
            )

        return results

    def close(self) -> None:
        """Clean up model resources and free GPU memory."""
        logger.info("Closing ExampleCustomDetector...")
        self._model = None
