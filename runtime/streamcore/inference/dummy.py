from time import monotonic

from ..types import CameraFrame, DetectionResult, InferenceBatch
from .base import Detector


class DummyDetector(Detector):
    def load(self) -> None:
        pass  # Deliberately no model or GPU resources.

    def warmup(self) -> None:
        pass

    def infer(self, batch: list[CameraFrame] | InferenceBatch) -> list[DetectionResult]:
        finished = monotonic()
        if isinstance(batch, InferenceBatch):
            return [DetectionResult(m.camera_id, m.sequence, m.timestamp, (), 0.0,
                                    max(0.0, (finished - m.received_monotonic) * 1000),
                                    m.width, m.height)
                    for m in batch.frames]
        return [DetectionResult(f.camera_id, f.sequence, f.timestamp, (), 0.0,
                                max(0.0, (finished - f.received_monotonic) * 1000),
                                f.width, f.height)
                for f in batch]

    def infer_gpu(self, batch: InferenceBatch) -> list[DetectionResult]:
        return self.infer(batch)

    def close(self) -> None:
        pass
