"""Visual Search Manager for Natural Language Surveillance Video Search.

Coordinates:
- Snapshot extraction and disk storage
- Local VLM description + local embedder (Ollama) with deterministic fallbacks
- FAISS vector store indexing; row <-> event mapping lives in SQLite (vector_id_map)
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any

import cv2
import numpy as np

from ..config import EventsConfig
from .local_models import LocalModelService
from .vector_store import FaissVectorStore

logger = logging.getLogger("events.visual_search")


class VisualSearchManager:
    """Manages 100% local visual embeddings, FAISS indexing, and natural language surveillance queries."""

    def __init__(
        self,
        base_dir: str | Path = "runtime/streamcore/output",
        event_db: Any = None,
        settings: Any = None,
        **kwargs: Any,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.snapshots_dir = self.base_dir / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir = self.base_dir / "vector_index"
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.event_db = event_db
        self.settings = settings
        self.min_crop_px = max(10, int(getattr(settings, "min_crop_px", 10) or 10))
        self.vector_store = FaissVectorStore(
            self.index_dir,
            event_db=event_db,
            dim=int(getattr(settings, "embed_dim", 0) or 0) or None,
        )
        self.local_models: LocalModelService = (
            LocalModelService(settings) if settings else LocalModelService(EventsConfig())
        )

        # Thread pool for asynchronous background embedding so video pipeline is never delayed
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="visual-indexer")
        self._indexed_events = set(self.vector_store.id_map)

        # Auto-recover/reindex in daemon background thread so CLI queries and short scripts exit cleanly
        try:
            t = threading.Thread(
                target=self.index_existing_clips_sync,
                args=(1000,),
                name="historical-indexer",
                daemon=True,
            )
            t.start()
        except Exception:
            pass

    @property
    def has_api_key(self) -> bool:
        if self.local_models is not None and self.local_models.has_vlm:
            return True
        return False

    def extract_and_save_snapshot(
        self,
        frame_bgr: np.ndarray,
        bbox_xyxy: tuple[float, float, float, float] | list[float],
        camera_id: str,
        timestamp_str: str,
        event_id: str,
    ) -> str | None:
        """Extract the object bounding box with 10% padding and save as JPEG snapshot.

        Returns relative path to snapshot from output/ (e.g. snapshots/CAM001/CAM001_...jpg).
        Crops smaller than ``events.min_crop_px`` per side are skipped.
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
                logger.debug("snapshot_crop_too_small", extra={
                    "event_id": event_id, "width": cx2 - cx1, "height": cy2 - cy1,
                    "min_crop_px": self.min_crop_px,
                })
                return None

            crop = frame_bgr[cy1:cy2, cx1:cx2]

            cam_dir = self.snapshots_dir / camera_id
            cam_dir.mkdir(parents=True, exist_ok=True)

            clean_ts = timestamp_str.replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")
            filename = f"{camera_id}_{clean_ts}_{event_id}.jpg"
            abs_path = cam_dir / filename

            success = cv2.imwrite(str(abs_path), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if success:
                rel_path = f"snapshots/{camera_id}/{filename}"
                return rel_path
        except Exception as exc:
            logger.error("extract_snapshot_failed", extra={"event_id": event_id, "reason": str(exc)})
        return None

    def index_event_async(
        self,
        event_id: str,
        camera_id: str,
        snapshot_rel_path: str,
        clip_rel_path: str,
        started_at_utc: str,
        track_id: str = "",
        bbox: list[float] | None = None,
        object_class: str = "",
    ) -> None:
        """Schedule local description + embedding generation and FAISS indexing."""
        if event_id in self._indexed_events:
            return
        self._indexed_events.add(event_id)
        self._executor.submit(
            self._do_index_event,
            event_id,
            camera_id,
            snapshot_rel_path,
            clip_rel_path,
            started_at_utc,
            track_id,
            bbox or [],
            object_class,
        )

    def _do_index_event(
        self,
        event_id: str,
        camera_id: str,
        snapshot_rel_path: str,
        clip_rel_path: str,
        started_at_utc: str,
        track_id: str,
        bbox: list[float],
        object_class: str = "",
    ) -> None:
        """Worker: describe the snapshot locally, embed it, and persist to FAISS + SQLite."""
        try:
            snap_p = Path(snapshot_rel_path)
            if snap_p.is_absolute() and snap_p.exists():
                abs_snap = snap_p
            elif (self.base_dir / snapshot_rel_path).exists():
                abs_snap = self.base_dir / snapshot_rel_path
            elif (self.snapshots_dir / snapshot_rel_path).exists():
                abs_snap = self.snapshots_dir / snapshot_rel_path
            elif snap_p.exists():
                abs_snap = snap_p
            else:
                clean_snap = snapshot_rel_path
                for pfx in ("runtime/streamcore/output/", "output/"):
                    if clean_snap.startswith(pfx):
                        clean_snap = clean_snap[len(pfx):]
                if (self.base_dir / clean_snap).exists():
                    abs_snap = self.base_dir / clean_snap
                elif (self.snapshots_dir / clean_snap).exists():
                    abs_snap = self.snapshots_dir / clean_snap
                else:
                    abs_snap = self.base_dir / clean_snap

            desc = self.local_models.describe_with_fallback(abs_snap, object_class=object_class)
            if not desc:
                desc = f"{object_class or 'object'} detected on surveillance camera"

            vec = self.local_models.embed_text(desc)

            if self.event_db is not None:
                row = self.vector_store.add(event_id, vec)
                if row < 0:
                    raise RuntimeError(f"faiss add rejected event {event_id}")
                self.event_db.update_track_event(
                    event_id=event_id,
                    description=desc,
                    snapshot_path=snapshot_rel_path,
                )
            else:
                metadata = {
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "track_id": str(track_id),
                    "started_at_utc": started_at_utc,
                    "snapshot_path": snapshot_rel_path,
                    "clip_path": clip_rel_path,
                    "description": desc,
                    "bbox": bbox,
                }
                row = self.vector_store.add(event_id, vec, metadata)
                if row < 0:
                    raise RuntimeError(f"faiss add rejected event {event_id}")

            logger.info("event_vector_indexed", extra={
                "event_id": event_id,
                "camera_id": camera_id,
                "row": row,
                "mode": "db" if self.event_db is not None else "legacy",
                "desc": desc[:60],
            })
        except Exception as exc:
            self._indexed_events.discard(event_id)
            logger.error("do_index_event_failed", extra={"event_id": event_id, "reason": str(exc)})

    def search(
        self,
        query: str,
        top_k: int = 2,
        camera_id: str | None = None,
        start_utc: str | None = None,
        end_utc: str | None = None,
    ) -> list[dict[str, Any]]:
        """Natural language visual surveillance search.
        
        Embeds query text, retrieves top_k nearest vectors from FAISS index,
        supports camera and time range filters, and returns enriched event records with video and snapshot URLs.
        """
        if not query or not query.strip() or top_k <= 0:
            return []

        cleaned_query = query.strip()

        # Parse natural language query intent (time windows, camera ID, visual semantics)
        # only if temporal or camera filters were not explicitly passed from UI
        if not start_utc and not end_utc:
            try:
                intent = self.local_models.parse_query_intent(cleaned_query)
                visual_query = intent.get("visual_query") or cleaned_query
                start_utc = intent.get("start_utc") or start_utc
                end_utc = intent.get("end_utc") or end_utc
                if not camera_id:
                    camera_id = intent.get("camera_id") or camera_id
            except Exception as exc:
                logger.debug("parse_query_intent_error", extra={"reason": str(exc)})
                visual_query = cleaned_query
        else:
            visual_query = cleaned_query

        if not visual_query or not visual_query.strip():
            visual_query = "person"

        query_vec = self.local_models.embed_text(visual_query)

        results = self.vector_store.search(
            query_vec,
            top_k=top_k,
            camera_id=camera_id,
            start_utc=start_utc,
            end_utc=end_utc,
        )

        # Ensure clean clip_url and snapshot_url fields for frontend
        for r in results:
            clip_path = str(r.get("clip_path") or "").strip()
            # Normalize prefix
            for pfx in ("runtime/streamcore/output/", "output/", "clips/"):
                if clip_path.startswith(pfx):
                    clip_path = clip_path[len(pfx):]
            r["clip_path"] = clip_path
            r["clip_url"] = f"/api/clips/{clip_path}" if clip_path else ""

            snap_path = str(r.get("snapshot_path") or "").strip()
            for pfx in ("runtime/streamcore/output/", "output/", "snapshots/"):
                if snap_path.startswith(pfx):
                    snap_path = snap_path[len(pfx):]
            r["snapshot_path"] = snap_path
            r["snapshot_url"] = f"/api/snapshots/{snap_path}" if snap_path else ""

        return results

    def _is_indexed(self, event_id: str) -> bool:
        """Whether an event already has a vector row (SQLite in DB mode, legacy id map otherwise)."""
        if event_id in self._indexed_events:
            return True
        if self.event_db is not None:
            try:
                return self.event_db.get_vector_row_for_event(event_id) is not None
            except Exception:
                return False
        return event_id in self.vector_store.id_map

    def index_existing_clips_sync(self, max_items: int = 500) -> int:
        """Scan existing snapshots and events in events.db to build FAISS index."""
        indexed_count = 0
        try:
            import sqlite3
            db_path = self.base_dir / "events.db"
            conn = None
            if db_path.exists():
                try:
                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                except Exception:
                    conn = None

            if conn is not None:
                try:
                    c = conn.cursor()
                    c.execute("""
                        SELECT event_id, camera_id, track_id, started_at_utc, clip_path, metadata,
                               object_class, snapshot_path
                        FROM track_events
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (max_items,))
                    rows = c.fetchall()

                    for row in rows:
                        event_id = row["event_id"]
                        if self._is_indexed(event_id):
                            continue

                        camera_id = row["camera_id"]
                        started_at_utc = row["started_at_utc"] or ""
                        track_id = row["track_id"]
                        meta = json.loads(row["metadata"]) if row["metadata"] else {}
                        bbox = meta.get("bbox") or []
                        object_class = row["object_class"] or meta.get("class") or ""

                        # Find snapshot on disk
                        rel_snap = row["snapshot_path"] or meta.get("snapshot_path") or ""
                        if rel_snap and not (self.base_dir / rel_snap).exists():
                            rel_snap = ""

                        if not rel_snap:
                            cam_snap_dir = self.snapshots_dir / camera_id
                            if cam_snap_dir.exists():
                                matches = list(cam_snap_dir.glob(f"*{event_id}*.jpg"))
                                if matches:
                                    try:
                                        rel_snap = str(matches[0].relative_to(self.base_dir))
                                    except Exception:
                                        rel_snap = f"snapshots/{camera_id}/{matches[0].name}"
                            if not rel_snap and self.snapshots_dir.exists():
                                matches = list(self.snapshots_dir.glob(f"*{event_id}*.jpg"))
                                if matches:
                                    try:
                                        rel_snap = str(matches[0].relative_to(self.base_dir))
                                    except Exception:
                                        rel_snap = f"snapshots/{matches[0].name}"

                        if rel_snap:
                            clip_rel = row["clip_path"] or ""
                            if not clip_rel:
                                clean_ts = started_at_utc.replace("-", "").replace(":", "").replace("T", "_").replace("Z", "")
                                clip_rel = f"clips/{camera_id}/{camera_id}_{clean_ts}_{event_id}.mp4"

                            self._do_index_event(
                                event_id=event_id,
                                camera_id=camera_id,
                                snapshot_rel_path=rel_snap,
                                clip_rel_path=clip_rel,
                                started_at_utc=started_at_utc,
                                track_id=str(track_id),
                                bbox=bbox,
                                object_class=object_class,
                            )
                            if self._is_indexed(event_id):
                                self._indexed_events.add(event_id)
                                indexed_count += 1
                except Exception as db_exc:
                    logger.warning("db_scan_failed", extra={"reason": str(db_exc)})

            # Also scan snapshots directory for unindexed files on disk (legacy mode only):
            # with an event DB attached, events.db is the single source of truth, so disk
            # files without a DB row must NOT become orphan pseudo-events.
            try:
                if self.event_db is not None:
                    snap_files = []
                else:
                    snap_files = sorted(self.snapshots_dir.glob("**/*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            except Exception:
                snap_files = [] if self.event_db is not None else list(self.snapshots_dir.glob("**/*.jpg"))

            for snap_path in snap_files:
                filename = snap_path.name
                stem = snap_path.stem
                parts = stem.split("_")
                if snap_path.parent == self.snapshots_dir:
                    camera_id = parts[0] if len(parts) >= 3 else "CAM001"
                else:
                    camera_id = snap_path.parent.name

                # Format: {camera_id}_{YYYYMMDD}_{HHMMSS}_{event_id}
                if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit():
                    event_id = "_".join(parts[3:])
                    ts_str = f"{parts[1]}_{parts[2]}"
                elif len(parts) >= 3 and parts[1].isdigit():
                    event_id = "_".join(parts[2:])
                    ts_str = parts[1]
                else:
                    event_id = parts[-1] if len(parts) >= 2 else stem
                    ts_str = ""

                if self._is_indexed(event_id):
                    continue

                started_at_utc = ""
                track_id = "-1"
                bbox = []
                expected_clip = ""
                object_class = ""

                # Correlate with events.db if possible
                if conn is not None:
                    try:
                        c = conn.cursor()
                        c.execute(
                            "SELECT track_id, started_at_utc, clip_path, metadata, object_class, snapshot_path "
                            "FROM track_events WHERE event_id = ?",
                            (event_id,),
                        )
                        db_row = c.fetchone()
                        if db_row:
                            track_id = str(db_row["track_id"] or "-1")
                            started_at_utc = db_row["started_at_utc"] or ""
                            expected_clip = db_row["clip_path"] or ""
                            object_class = db_row["object_class"] or ""
                            m = json.loads(db_row["metadata"]) if db_row["metadata"] else {}
                            bbox = m.get("bbox") or []
                    except Exception:
                        pass

                if not started_at_utc and ts_str:
                    try:
                        dt = datetime.strptime(ts_str[:15], "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                        started_at_utc = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        started_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                elif not started_at_utc:
                    started_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                try:
                    rel_snap = str(snap_path.relative_to(self.base_dir))
                except Exception:
                    rel_snap = f"snapshots/{camera_id}/{filename}"

                if not expected_clip:
                    expected_clip = f"clips/{camera_id}/{filename.replace('.jpg', '.mp4')}"

                self._do_index_event(
                    event_id=event_id,
                    camera_id=camera_id,
                    snapshot_rel_path=rel_snap,
                    clip_rel_path=expected_clip,
                    started_at_utc=started_at_utc,
                    track_id=track_id,
                    bbox=bbox,
                    object_class=object_class,
                )
                if self._is_indexed(event_id):
                    self._indexed_events.add(event_id)
                    indexed_count += 1

            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

            if indexed_count > 0:
                self.vector_store.save()
                logger.info("indexed_existing_snapshots_completed", extra={"indexed_count": indexed_count, "total_in_index": self.vector_store.total_items})

        except Exception as exc:
            logger.error("index_existing_clips_failed", extra={"reason": str(exc)})
        return indexed_count

    def shutdown(self) -> None:
        try:
            self._executor.shutdown(wait=False)
            self.vector_store.save()
        except Exception:
            pass
