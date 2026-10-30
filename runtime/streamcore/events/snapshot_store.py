"""Event snapshot storage.

Saves a padded bounding-box crop of the triggering frame as a JPEG thumbnail.
Snapshots are used by the events UI only; there is no VLM or embedding step.

This replaces the snapshot extraction that previously lived inside
``VisualSearchManager`` so the events pipeline keeps working without the
visual-search stack.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2

logger = logging.getLogger("events.snapshots")

DEFAULT_MIN_CROP_PX = 40


class SnapshotStore:
    """Writes per-camera event thumbnails under ``<base_dir>/snapshots``."""

    def __init__(
        self,
        base_dir: str | Path = "runtime/streamcore/output",
        min_crop_px: int = DEFAULT_MIN_CROP_PX,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.snapshots_dir = self.base_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.min_crop_px = int(min_crop_px)

    def extract_and_save_snapshot(
        self,
        frame_bgr: Any,
        bbox_xyxy: tuple[float, float, float, float] | list[float] | None,
        camera_id: str,
        timestamp_str: str,
        event_id: str,
    ) -> str | None:
        """Save a 10%-padded crop of ``bbox_xyxy`` and return its relative path.

        Returns paths like ``snapshots/CAM001/CAM001_...jpg`` relative to the
        output directory. Crops smaller than ``min_crop_px`` per side are
        skipped.
        """
        try:
            if frame_bgr is None or not hasattr(frame_bgr, "shape"):
                return None

            h, w = frame_bgr.shape[:2]
            if bbox_xyxy is None or len(bbox_xyxy) < 4:
                x1, y1, x2, y2 = 0.0, 0.0, float(w), float(h)
            else:
                x1, y1, x2, y2 = bbox_xyxy

            # Handle normalized coordinates if needed
            if x2 <= 1.0 and y2 <= 1.0 and w > 1 and h > 1:
                x1 *= w
                x2 *= w
                y1 *= h
                y2 *= h

            bw = max(1.0, x2 - x1)
            bh = max(1.0, y2 - y1)
            pad_x = bw * 0.10
            pad_y = bh * 0.10

            cx1 = max(0, int(x1 - pad_x))
            cy1 = max(0, int(y1 - pad_y))
            cx2 = min(w, int(x2 + pad_x))
            cy2 = min(h, int(y2 + pad_y))

            if cx2 <= cx1 + self.min_crop_px or cy2 <= cy1 + self.min_crop_px:
                logger.debug(
                    "snapshot_crop_too_small",
                    extra={
                        "event_id": event_id,
                        "width": cx2 - cx1,
                        "height": cy2 - cy1,
                        "min_crop_px": self.min_crop_px,
                    },
                )
                return None

            crop = frame_bgr[cy1:cy2, cx1:cx2]

            cam_dir = self.snapshots_dir / camera_id
            cam_dir.mkdir(parents=True, exist_ok=True)

            clean_ts = (
                timestamp_str.replace("-", "")
                .replace(":", "")
                .replace("T", "_")
                .replace("Z", "")
            )
            filename = f"{camera_id}_{clean_ts}_{event_id}.jpg"
            abs_path = cam_dir / filename

            success = cv2.imwrite(
                str(abs_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 90]
            )
            if success:
                return f"snapshots/{camera_id}/{filename}"
        except Exception as exc:
            logger.error(
                "extract_snapshot_failed",
                extra={"event_id": event_id, "reason": str(exc)},
            )
        return None
