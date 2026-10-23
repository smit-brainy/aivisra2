from dataclasses import dataclass

from ..types import CameraFrame


@dataclass(frozen=True, slots=True)
class TrackFrame:
    frame: CameraFrame
    confidence: float
    blur_score: float = 0.0
    object_area_ratio: float = 0.0


class KeyFrameSelector:
    """Choose a small, time-distributed set of best original frames."""

    def __init__(self, limit: int = 3) -> None:
        if not 1 <= limit <= 5:
            raise ValueError("limit must be between 1 and 5")
        self.limit = limit

    @staticmethod
    def _score(candidate: TrackFrame) -> float:
        sharpness = max(0.0, min(candidate.blur_score / 500.0, 1.0))
        size = max(0.0, min(candidate.object_area_ratio, 1.0))
        return candidate.confidence * 0.6 + sharpness * 0.2 + size * 0.2

    def select(self, candidates: list[TrackFrame]) -> list[TrackFrame]:
        unique = {item.frame.sequence: item for item in candidates}
        return sorted(unique.values(), key=self._score, reverse=True)[:self.limit]
