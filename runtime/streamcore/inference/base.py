from abc import ABC, abstractmethod

from ..types import CameraFrame, DetectionResult, InferenceBatch


class Detector(ABC):
    """One engine-owned instance, called serially with bounded batches."""

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def warmup(self) -> None: ...

    @abstractmethod
    def infer(self, batch: list[CameraFrame] | InferenceBatch) -> list[DetectionResult]: ...

    @abstractmethod
    def close(self) -> None: ...
