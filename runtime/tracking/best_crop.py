from __future__ import annotations

import math
from typing import Any

from .types import BestCropMetadata, Track


class BestCropSelector:
    """Evaluates detection quality and retains the best representative crop per track."""

    def __init__(self, minimum_improvement: float = 0.05) -> None:
        self.minimum_improvement = minimum_improvement

    def evaluate_candidate(
        self,
        bbox_xyxy: tuple[float, float, float, float],
        confidence: float,
        source_width: int,
        source_height: int,
        frame_image: Any = None,
        class_name: str = "person",
    ) -> float:
        """Compute a normalized quality score between 0.0 and 1.0."""
        x1, y1, x2, y2 = bbox_xyxy
        bw = max(1.0, x2 - x1)
        bh = max(1.0, y2 - y1)
        sw = max(1, source_width)
        sh = max(1, source_height)

        # 1. Detection confidence (weight: 0.35)
        s_conf = min(1.0, max(0.0, confidence))

        # 2. Bounding box size / resolution (weight: 0.25)
        area_ratio = (bw * bh) / float(sw * sh)
        # Optimal candidate occupies ~3% to ~25% of frame
        s_size = min(1.0, max(0.0, math.sqrt(area_ratio) / 0.35))

        # 3. Center position preference (weight: 0.15)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        norm_dist_x = (cx - (sw / 2.0)) / (sw / 2.0)
        norm_dist_y = (cy - (sh / 2.0)) / (sh / 2.0)
        dist_from_center = math.hypot(norm_dist_x, norm_dist_y) / 1.4142
        s_center = max(0.1, 1.0 - (0.6 * min(1.0, dist_from_center)))

        # 4. Edge clipping penalty (weight: 0.15)
        is_clipped = (x1 <= 4.0) or (y1 <= 4.0) or (x2 >= (sw - 4.0)) or (y2 >= (sh - 4.0))
        s_edge = 0.25 if is_clipped else 1.0

        # 5. Aspect ratio / visibility (weight: 0.10)
        ar = bw / bh
        if class_name == "person":
            # Typical standing/walking person aspect ratio is 0.35 - 0.55
            diff = abs(ar - 0.45)
            s_aspect = max(0.2, 1.0 - (diff / 0.5))
        else:
            s_aspect = 0.8

        # 6. Optional Sharpness (only if CPU frame image is readily available)
        s_sharp = 1.0
        if frame_image is not None and hasattr(frame_image, "shape"):
            try:
                import cv2
                import numpy as np

                ix1 = max(0, int(x1))
                iy1 = max(0, int(y1))
                ix2 = min(sw, int(x2))
                iy2 = min(sh, int(y2))
                if ix2 > ix1 + 10 and iy2 > iy1 + 10:
                    crop = frame_image[iy1:iy2, ix1:ix2]
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
                    var = cv2.Laplacian(gray, cv2.CV_64F).var()
                    # Normalized sharpness: 100+ variance is sharp
                    s_sharp = min(1.0, max(0.1, var / 150.0))
            except Exception:
                s_sharp = 1.0

        # Weighted combination
        score = (
            (0.35 * s_conf)
            + (0.25 * s_size)
            + (0.15 * s_center)
            + (0.15 * s_edge)
            + (0.10 * s_aspect)
        ) * s_sharp

        return round(min(1.0, max(0.0, score)), 4)

    def maybe_update(
        self,
        track: Track,
        bbox_xyxy: tuple[float, float, float, float],
        confidence: float,
        timestamp_ns: int,
        frame_sequence: int,
        source_width: int,
        source_height: int,
        frame_image: Any = None,
    ) -> bool:
        """Evaluate candidate and update track best crop if improvement >= threshold."""
        score = self.evaluate_candidate(
            bbox_xyxy,
            confidence,
            source_width,
            source_height,
            frame_image=frame_image,
            class_name=track.class_name,
        )

        if score - track.best_crop_score >= self.minimum_improvement:
            image_bytes = None
            if frame_image is not None:
                image_bytes = self._encode_crop(frame_image, bbox_xyxy, source_width, source_height)

            track.best_crop_score = score
            track.best_crop_metadata = BestCropMetadata(
                track_id=track.global_track_id,
                camera_id=track.camera_id,
                frame_sequence=frame_sequence,
                timestamp_ns=timestamp_ns,
                bbox_xyxy=bbox_xyxy,
                quality_score=score,
                image_bytes=image_bytes,
                width=int(max(1.0, bbox_xyxy[2] - bbox_xyxy[0])),
                height=int(max(1.0, bbox_xyxy[3] - bbox_xyxy[1])),
            )
            return True
        return False

    def _encode_crop(
        self,
        image: Any,
        bbox_xyxy: tuple[float, float, float, float],
        sw: int,
        sh: int,
    ) -> bytes | None:
        """Extract and JPEG-encode bounding box crop."""
        try:
            import cv2
            x1 = max(0, int(bbox_xyxy[0]))
            y1 = max(0, int(bbox_xyxy[1]))
            x2 = min(sw, int(bbox_xyxy[2]))
            y2 = min(sh, int(bbox_xyxy[3]))
            if x2 <= x1 or y2 <= y1:
                return None
            crop = image[y1:y2, x1:x2]
            success, enc = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if success:
                return bytes(enc)
        except Exception:
            pass
        return None

