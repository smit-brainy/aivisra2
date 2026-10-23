from pathlib import Path
import re

from ..types import CameraFrame
from .storage_base import EvidenceStorage


class LocalEvidenceStorage(EvidenceStorage):
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save_frame(self, frame: CameraFrame, category: str,
                   object_id: str, *, quality: int = 90) -> Path:
        if category not in ("tracks", "events"):
            raise ValueError("category must be tracks or events")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", object_id):
            raise ValueError("invalid object_id")
        if not 1 <= quality <= 100:
            raise ValueError("quality must be between 1 and 100")
        import cv2
        ok, encoded = cv2.imencode(".jpg", frame.image,
                                  [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("evidence-jpeg-encode-failed")
        directory = self.root / frame.camera_id / category
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{object_id}-{frame.sequence}.jpg"
        temporary = destination.with_suffix(".jpg.tmp")
        temporary.write_bytes(encoded.tobytes())
        temporary.replace(destination)
        return destination
