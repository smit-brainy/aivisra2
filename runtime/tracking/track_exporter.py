from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from ..streamcore.types import DetectionResult
from .types import Track


class TracksJsonWriter:
    """Exports detection and tracking telemetry to JSON or JSONL format.

    Supported formats:
    - JSON Lines (.jsonl, .ndjson): Writes one valid JSON record per line in real-time.
    - JSON Array (.json): Writes an open streaming JSON array '[' and closes with ']' on completion.

    Records include:
    - id: Local integer track ID (or None if untracked)
    - track_id: Global track ID string (e.g. 'CAM001_1')
    - camera_id: Camera identifier (e.g. 'CAM001')
    - bbox: Source pixel bounding box [x1, y1, x2, y2]
    - bbox_xywh: Bounding box [x, y, width, height]
    - label: Detection class name (e.g. 'person')
    - class_id: Integer class ID
    - confidence: Detection confidence score
    - frame_sequence: Sequence index of the processed frame
    - timestamp: Receipt timestamp (Unix epoch seconds)
    - tracking: Telemetry dictionary (state, direction, duration_ms, velocity, hit_count, trajectory)
    """

    def __init__(self, path: str | Path, record_format: str = "records") -> None:
        self.path = Path(path)
        self.record_format = record_format
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._is_jsonl = self.path.suffix.lower() in (".jsonl", ".ndjson")
        self.file = self.path.open("w", encoding="utf-8")
        self._first_item = True
        self._closed = False

        if not self._is_jsonl:
            self.file.write("[\n")
            self.file.flush()

    def write_results(
        self,
        results: list[DetectionResult],
        tracks_by_camera: dict[str, list[Track]] | None = None,
    ) -> None:
        """Write detections and associated tracking telemetry from inference results."""
        with self._lock:
            if self._closed or not results:
                return

            tracks_by_camera = tracks_by_camera or {}

            for res in results:
                w = getattr(res, "source_width", 0) or 1280
                h = getattr(res, "source_height", 0) or 720
                c_tracks = tracks_by_camera.get(res.camera_id, [])
                tracks_map = {t.global_track_id: t for t in c_tracks}

                frame_records = []
                for d in res.detections:
                    tid = getattr(d, "track_id", None)
                    trk = tracks_map.get(tid) if tid else None

                    if d.normalized:
                        x1 = round(d.x1 * w, 1)
                        y1 = round(d.y1 * h, 1)
                        x2 = round(d.x2 * w, 1)
                        y2 = round(d.y2 * h, 1)
                    else:
                        x1 = round(d.x1, 1)
                        y1 = round(d.y1, 1)
                        x2 = round(d.x2, 1)
                        y2 = round(d.y2, 1)

                    local_id = trk.local_track_id if trk else None
                    if local_id is None and tid:
                        for sep in (":", "_"):
                            if sep in tid:
                                try:
                                    local_id = int(tid.rsplit(sep, 1)[-1])
                                    break
                                except ValueError:
                                    pass

                    rec: dict[str, Any] = {
                        "id": local_id,
                        "track_id": tid,
                        "camera_id": res.camera_id,
                        "bbox": [x1, y1, x2, y2],
                        "bbox_xywh": [x1, y1, round(x2 - x1, 1), round(y2 - y1, 1)],
                        "label": d.label,
                        "class_id": d.class_id,
                        "confidence": round(d.confidence, 4),
                        "frame_sequence": res.frame_sequence,
                        "timestamp": res.timestamp,
                        "tracking": {
                            "state": str(trk.state) if trk else "UNTRACKED",
                            "direction": str(trk.direction) if trk else "STATIONARY",
                            "duration_ms": round(trk.duration_ms, 1) if trk else 0.0,
                            "velocity": [round(trk.velocity[0], 2), round(trk.velocity[1], 2)] if trk else [0.0, 0.0],
                            "hit_count": trk.hit_count if trk else 1,
                            "miss_count": trk.miss_count if trk else 0,
                            "trajectory": [[round(p[0], 1), round(p[1], 1)] for p in list(trk.trajectory)[-20:]] if trk else [],
                        },
                    }
                    frame_records.append(rec)

                if self.record_format == "frames":
                    frame_rec = {
                        "camera_id": res.camera_id,
                        "frame_sequence": res.frame_sequence,
                        "timestamp": res.timestamp,
                        "detections_count": len(frame_records),
                        "tracks": frame_records,
                    }
                    self._write_item(frame_rec)
                else:
                    for rec in frame_records:
                        self._write_item(rec)

            self.file.flush()

    def _write_item(self, item: dict[str, Any]) -> None:
        line = json.dumps(item)
        if self._is_jsonl:
            self.file.write(line + "\n")
        else:
            if not self._first_item:
                self.file.write(",\n")
            self.file.write("  " + line)
            self._first_item = False

    def close(self) -> None:
        """Finalize and close output file stream."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                if not self._is_jsonl:
                    self.file.write("\n]\n")
                self.file.flush()
                self.file.close()
            except Exception:
                pass

    def __enter__(self) -> TracksJsonWriter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
