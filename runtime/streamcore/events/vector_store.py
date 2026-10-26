"""FAISS Vector Store for semantic surveillance search.

Stores 768-dimensional visual embeddings linked to track events, person snapshots,
and recorded 10-second MP4 video clips.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

import faiss
import numpy as np

logger = logging.getLogger("events.vector_store")

VECTOR_DIM = 768


class FaissVectorStore:
    """Thread-safe vector store backed by FAISS IndexFlatIP (Cosine Similarity)."""

    def __init__(
        self,
        storage_dir: str | Path = "runtime/streamcore/output/vector_index",
        event_db: Any = None,
        dim: int | None = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_dir / "faiss.index"
        self.metadata_path = self.storage_dir / "metadata.json"

        self._lock = threading.RLock()
        self.dim = int(dim or VECTOR_DIM)
        self.event_db = event_db

        # In-memory mapping
        self.id_map: list[str] = []  # Index position -> event_id
        self.metadata_map: dict[str, dict[str, Any]] = {}  # legacy mode only
        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(self.dim)

        self._load()
        # Guarantee the index file exists on disk immediately upon startup
        self._ensure_files_exist()

    def _ensure_files_exist(self) -> None:
        """Guarantee storage directory and index file exist on disk."""
        with self._lock:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            if self.event_db is not None:
                if not self.index_path.is_file():
                    self.save()
                return
            if not self.index_path.is_file() or not self.metadata_path.is_file():
                self.save()

    def _load(self) -> None:
        """Load the index; the id map comes from SQLite when an event DB is attached."""
        with self._lock:
            if self.event_db is not None:
                self._load_db_mode()
                return
            try:
                if self.metadata_path.exists():
                    with open(self.metadata_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.id_map = data.get("id_map", [])
                        self.metadata_map = data.get("metadata", {})

                if self.index_path.exists() and len(self.id_map) > 0:
                    loaded_index = faiss.read_index(str(self.index_path))
                    if loaded_index.ntotal == len(self.id_map):
                        self.index = loaded_index
                        logger.info("vector_store_loaded", extra={
                            "total_vectors": self.index.ntotal,
                            "path": str(self.index_path)
                        })
                        return
                    elif loaded_index.ntotal > 0:
                        min_len = min(loaded_index.ntotal, len(self.id_map))
                        logger.warning("vector_store_count_reconciled", extra={
                            "index_total": loaded_index.ntotal,
                            "id_map_len": len(self.id_map),
                            "reconciled": min_len,
                        })
                        self.id_map = self.id_map[:min_len]
                        valid_ids = set(self.id_map)
                        self.metadata_map = {k: v for k, v in self.metadata_map.items() if k in valid_ids}
                        if loaded_index.ntotal > min_len:
                            try:
                                new_index = faiss.IndexFlatIP(self.dim)
                                raw_vecs = loaded_index.reconstruct_n(0, min_len)
                                new_index.add(raw_vecs)
                                self.index = new_index
                            except Exception:
                                self.index = loaded_index
                        else:
                            self.index = loaded_index
                        self.save()
                        return
                    else:
                        logger.warning("vector_store_count_mismatch", extra={
                            "index_total": loaded_index.ntotal,
                            "id_map_len": len(self.id_map)
                        })
            except Exception as exc:
                logger.error("vector_store_load_failed", extra={"reason": str(exc)})

            # Auto-create fresh index and write files immediately to disk
            self.index = faiss.IndexFlatIP(self.dim)
            self.id_map = []
            self.metadata_map = {}
            self.save()

    def _load_db_mode(self) -> None:
        """Load index + reconcile the SQLite vector_id_map with the FAISS file."""
        rows = self.event_db.all_vector_rows()
        self.id_map = [event_id for _row, event_id in rows]
        self.metadata_map = {}
        try:
            if self.index_path.exists() and len(self.id_map) > 0:
                loaded_index = faiss.read_index(str(self.index_path))
                if loaded_index.ntotal == len(self.id_map):
                    self.index = loaded_index
                    logger.info("vector_store_loaded_db_mode", extra={
                        "total_vectors": self.index.ntotal, "path": str(self.index_path)
                    })
                    return
                if loaded_index.ntotal > len(self.id_map):
                    logger.warning("vector_store_index_orphans_trimmed", extra={
                        "index_total": loaded_index.ntotal, "id_map_len": len(self.id_map)
                    })
                    new_index = faiss.IndexFlatIP(self.dim)
                    if len(self.id_map) > 0:
                        raw = loaded_index.reconstruct_n(0, len(self.id_map))
                        new_index.add(raw)
                    self.index = new_index
                    self.save()
                    return
                logger.warning("vector_store_db_rows_orphaned", extra={
                    "index_total": loaded_index.ntotal, "id_map_len": len(self.id_map)
                })
                for row, _event_id in rows[loaded_index.ntotal:]:
                    self.event_db.delete_vector_row(row)
                self.id_map = self.id_map[: loaded_index.ntotal]
                self.index = loaded_index
                return
            if self.index_path.exists() and len(self.id_map) == 0:
                loaded_index = faiss.read_index(str(self.index_path))
                if loaded_index.ntotal == 0:
                    self.index = loaded_index
                    return
                raise RuntimeError("faiss index has vectors but SQLite vector_id_map is empty; dropping orphan vectors")
        except Exception as exc:
            logger.error("vector_store_db_load_failed", extra={"reason": str(exc)})
            for row, _event_id in self.event_db.all_vector_rows():
                self.event_db.delete_vector_row(row)
            self.id_map = []
            self.index = faiss.IndexFlatIP(self.dim)
            self.save()

    def save(self) -> None:
        """Atomically persist the FAISS index (and legacy metadata sidecar, if in legacy mode)."""
        with self._lock:
            try:
                self.storage_dir.mkdir(parents=True, exist_ok=True)
                tmp_idx = self.storage_dir / "faiss.index.tmp"
                faiss.write_index(self.index, str(tmp_idx))
                os.replace(tmp_idx, self.index_path)

                if self.event_db is None:
                    tmp_meta = self.storage_dir / "metadata.json.tmp"
                    with open(tmp_meta, "w", encoding="utf-8") as f:
                        json.dump({
                            "id_map": self.id_map,
                            "metadata": self.metadata_map
                        }, f, indent=2)
                    os.replace(tmp_meta, self.metadata_path)
            except Exception as exc:
                logger.error("vector_store_save_failed", extra={"reason": str(exc)})

    def add(
        self,
        event_id: str,
        vector: np.ndarray | list[float],
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Add an event embedding; returns the FAISS row position, or -1 on failure.

        With an attached event DB, the row <-> event mapping is recorded in SQLite
        and no JSON sidecar is written. Without one, legacy metadata is kept in
        the sidecar file.
        """
        with self._lock:
            self._ensure_files_exist()
            try:
                vec = np.asarray(vector, dtype=np.float32).reshape(1, -1)
                if vec.shape[1] != self.dim:
                    logger.error("invalid_vector_dim", extra={"expected": self.dim, "got": vec.shape[1]})
                    return -1
                if not np.all(np.isfinite(vec)):
                    vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
                norm = float(np.linalg.norm(vec))
                if norm <= 1e-6:
                    logger.warning("zero_norm_vector_rejected", extra={"event_id": event_id})
                    return -1

                # Normalize for Cosine Similarity
                faiss.normalize_L2(vec)

                if event_id in self.id_map:
                    if self.event_db is None and metadata is not None:
                        self.metadata_map.setdefault(event_id, {}).update(metadata)
                        self.save()
                    row = self.id_map.index(event_id)
                    return row

                row = int(self.index.ntotal)
                if self.event_db is not None:
                    if not self.event_db.record_vector_row(row, event_id):
                        return -1
                self.index.add(vec)
                self.id_map.append(event_id)
                if self.event_db is None:
                    self.metadata_map[event_id] = metadata or {}
                self.save()
                return row
            except Exception as exc:
                logger.error("vector_store_add_failed", extra={"event_id": event_id, "reason": str(exc)})
                return -1

    def search(
        self,
        query_vector: np.ndarray | list[float],
        top_k: int = 2,
        camera_id: str | None = None,
        start_utc: str | None = None,
        end_utc: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search top_k closest events using cosine similarity.
        
        Supports optional filtering by camera_id, start_utc, and end_utc.
        Returns list of dicts with:
            event_id, similarity (0.0 - 1.0), camera_id, clip_path, snapshot_path, description, etc.
        """
        with self._lock:
            self._ensure_files_exist()
            if self.index.ntotal == 0 or top_k <= 0:
                return []

            try:
                q = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
                if q.shape[1] != self.dim:
                    logger.warning("invalid_query_vector_dim", extra={"expected": self.dim, "got": q.shape[1]})
                    return []
                if not np.all(np.isfinite(q)):
                    q = np.nan_to_num(q, nan=0.0, posinf=0.0, neginf=0.0)
                norm = float(np.linalg.norm(q))
                if norm <= 1e-6:
                    return []

                faiss.normalize_L2(q)

                # Retrieve more candidates if camera or time filters are requested
                has_filters = bool(camera_id or start_utc or end_utc)
                fetch_k = max(1, min(self.index.ntotal, max(top_k * 50, 1000) if has_filters else max(top_k * 2, 10)))
                distances, indices = self.index.search(q, fetch_k)

                def _norm_iso(ts: str | None) -> str:
                    if not ts:
                        return ""
                    return ts.strip().replace(" ", "T").rstrip("Z")

                n_start = _norm_iso(start_utc)
                n_end = _norm_iso(end_utc)
                cam_filter = (camera_id or "").strip().upper()

                # Batch fetch event metadata from SQLite when event_db is attached
                candidate_ids = [
                    self.id_map[idx]
                    for idx in indices[0]
                    if 0 <= idx < len(self.id_map)
                ]
                db_meta_map: dict[str, dict[str, Any]] = {}
                if self.event_db is not None and candidate_ids:
                    try:
                        db_meta_map = self.event_db.get_events_by_ids(candidate_ids)
                    except Exception as ex:
                        logger.warning("fetch_event_db_meta_failed", extra={"reason": str(ex)})

                results = []
                for score, idx in zip(distances[0], indices[0]):
                    if idx < 0 or idx >= len(self.id_map):
                        continue
                    event_id = self.id_map[idx]
                    meta = db_meta_map.get(event_id) if self.event_db is not None else self.metadata_map.get(event_id, {})
                    if not meta:
                        meta = {}

                    cam_val = str(meta.get("camera_id") or "").strip().upper()
                    if cam_filter and cam_val and cam_val != cam_filter:
                        continue

                    evt_time = meta.get("started_at_utc")
                    if evt_time:
                        n_evt = _norm_iso(evt_time)
                        if n_start and n_evt < n_start:
                            continue
                        if n_end and n_evt > n_end:
                            continue

                    # Clamp similarity score to [0.0, 1.0]
                    sim = max(0.0, min(1.0, float(score)))
                    item = {
                        "event_id": event_id,
                        "similarity": round(sim, 4),
                        "similarity_percent": round(sim * 100, 1),
                        **meta
                    }
                    results.append(item)
                    if len(results) >= top_k:
                        break

                return results
            except Exception as exc:
                logger.error("vector_store_search_failed", extra={"reason": str(exc)})
                return []

    def get_event_meta(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            if self.event_db is not None:
                events = self.event_db.get_events_by_ids([event_id])
                return events.get(event_id)
            return self.metadata_map.get(event_id)

    @property
    def total_items(self) -> int:
        with self._lock:
            return self.index.ntotal

