from abc import ABC, abstractmethod
from pathlib import Path

from ..types import CameraFrame


class EvidenceStorage(ABC):
    @abstractmethod
    def save_frame(self, frame: CameraFrame, category: str,
                   object_id: str, *, quality: int = 90) -> Path:
        """Persist one selected original-quality frame and return its location."""
