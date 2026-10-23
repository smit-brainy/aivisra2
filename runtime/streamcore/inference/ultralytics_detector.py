from time import monotonic, time
from typing import Any

import numpy as np

from ..config import InferenceConfig
from ..gpu_frame import unletterbox_boxes
from ..types import CameraFrame, Detection, DetectionResult, InferenceBatch
from .base import Detector


class UltralyticsDetector(Detector):
    def __init__(self, config: InferenceConfig) -> None:
        self.config = config
        self._model: Any = None
        self._batch_counter = 0

    def load(self) -> None:
        import os
        os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
        from ultralytics import YOLO  # Dummy mode never imports YOLO or torch.
        self._model = YOLO(self.config.model_path, task="detect")

    def warmup(self) -> None:
        image = np.zeros((self.config.imgsz, self.config.imgsz, 3), dtype=np.uint8)
        self.infer([CameraFrame("warmup", 0, time(), monotonic(), image,
                                self.config.imgsz, self.config.imgsz)])

    import torch

    @torch.inference_mode()
    def infer_gpu(self, batch: InferenceBatch) -> list[DetectionResult]:
        if self._model is None:
            raise RuntimeError("Detector has not been loaded")
        if not batch.frames or batch.batch_size == 0:
            return []
        started = monotonic()
        predictions = self._model.predict(
            source=batch.tensor, device=self.config.device,
            imgsz=self.config.imgsz, half=self.config.half,
            batch=batch.batch_size, stream=False, verbose=False, save=False, rect=False,
        )
        if len(predictions) != batch.batch_size:
            raise RuntimeError("Detector result count does not match input batch")

        rows: list[tuple[Detection, ...]] = []
        for meta, prediction in zip(batch.frames, predictions, strict=True):
            detections = []
            if prediction.boxes is not None and len(prediction.boxes) > 0:
                boxes_data = prediction.boxes.data.cpu().tolist()
                for x1, y1, x2, y2, confidence, class_id in boxes_data:
                    unmapped = unletterbox_boxes([[x1, y1, x2, y2]], meta.scale, meta.pad_x, meta.pad_y, meta.width, meta.height)
                    ux1, uy1, ux2, uy2 = unmapped[0]
                    norm_x1 = max(0.0, min(1.0, ux1 / meta.width)) if meta.width else 0.0
                    norm_y1 = max(0.0, min(1.0, uy1 / meta.height)) if meta.height else 0.0
                    norm_x2 = max(0.0, min(1.0, ux2 / meta.width)) if meta.width else 0.0
                    norm_y2 = max(0.0, min(1.0, uy2 / meta.height)) if meta.height else 0.0
                    detections.append(Detection(
                        int(class_id), str(prediction.names[int(class_id)]), float(confidence),
                        norm_x1, norm_y1, norm_x2, norm_y2,
                    ))
            rows.append(tuple(detections))
        finished = monotonic()
        elapsed = (finished - started) * 1000.0
        self._batch_counter += 1
        if self._batch_counter % 200 == 0:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        return [DetectionResult(meta.camera_id, meta.sequence, meta.timestamp, detections,
                                elapsed, max(0.0, (finished - meta.received_monotonic) * 1000.0),
                                meta.width, meta.height)
                for meta, detections in zip(batch.frames, rows, strict=True)]

    import torch

    @torch.inference_mode()
    def infer(self, batch: list[CameraFrame] | InferenceBatch) -> list[DetectionResult]:
        if isinstance(batch, InferenceBatch):
            return self.infer_gpu(batch)

        if self._model is None:
            raise RuntimeError("Detector has not been loaded")
        if not batch:
            return []
        started = monotonic()
        predictions = self._model.predict(
            source=[f.image for f in batch], device=self.config.device,
            imgsz=self.config.imgsz, half=self.config.half,
            batch=len(batch), stream=False, verbose=False, save=False, rect=False,
        )
        if len(predictions) != len(batch):
            raise RuntimeError("Detector result count does not match input batch")
        rows = []
        for frame, prediction in zip(batch, predictions, strict=True):
            detections = []
            if prediction.boxes is not None:
                # CPU transfer synchronizes GPU completion before timing the batch.
                for x1, y1, x2, y2, confidence, class_id in prediction.boxes.data.cpu().tolist():
                    detections.append(Detection(
                        int(class_id), str(prediction.names[int(class_id)]), float(confidence),
                        float(x1) / frame.width, float(y1) / frame.height,
                        float(x2) / frame.width, float(y2) / frame.height,
                    ))
            rows.append(tuple(detections))
        finished = monotonic()
        elapsed = (finished - started) * 1000
        self._batch_counter += 1
        if self._batch_counter % 200 == 0:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        return [DetectionResult(f.camera_id, f.sequence, f.timestamp, detections,
                                elapsed, max(0.0, (finished - f.received_monotonic) * 1000),
                                f.width, f.height)
                for f, detections in zip(batch, rows, strict=True)]

    def close(self) -> None:
        self._model = None
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
