import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import EventsConfig

logger = logging.getLogger("events.db")


@dataclass(slots=True)
class TrackEvent:
    event_id: str
    track_id: str
    track_session_id: str
    camera_id: str
    event_type: str
    object_class: str
    started_at_utc: str
    ended_at_utc: str | None
    duration_seconds: float | None
    max_confidence: float
    avg_confidence: float
    clip_path: str | None
    clip_recorded: bool
    metadata: dict[str, Any]
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "track_id": self.track_id,
            "track_session_id": self.track_session_id,
            "camera_id": self.camera_id,
            "event_type": self.event_type,
            "object_class": self.object_class,
            "started_at_utc": self.started_at_utc,
            "ended_at_utc": self.ended_at_utc,
            "duration_seconds": self.duration_seconds,
            "max_confidence": self.max_confidence,
            "avg_confidence": self.avg_confidence,
            "clip_path": self.clip_path,
            "clip_recorded": self.clip_recorded,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TrackEvent":
        return cls(
            event_id=row["event_id"],
            track_id=row["track_id"],
            track_session_id=row["track_session_id"],
            camera_id=row["camera_id"],
            event_type=row["event_type"],
            object_class=row["object_class"],
            started_at_utc=row["started_at_utc"],
            ended_at_utc=row["ended_at_utc"],
            duration_seconds=row["duration_seconds"],
            max_confidence=row["max_confidence"],
            avg_confidence=row["avg_confidence"],
            clip_path=row["clip_path"],
            clip_recorded=bool(row["clip_recorded"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class EventDatabase:
    def __init__(self, config: EventsConfig) -> None:
        self.config = config
        self.db_path = Path(config.clip_storage_dir).parent / "events.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._local = threading.local()
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS track_events (
                    event_id TEXT PRIMARY KEY,
                    track_id TEXT NOT NULL,
                    track_session_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    object_class TEXT NOT NULL,
                    started_at_utc TEXT NOT NULL,
                    ended_at_utc TEXT,
                    duration_seconds REAL,
                    max_confidence REAL,
                    avg_confidence REAL,
                    clip_path TEXT,
                    clip_recorded BOOLEAN DEFAULT 0,
                    metadata TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_camera_time
                ON track_events(camera_id, started_at_utc)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_track
                ON track_events(track_id, track_session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_active
                ON track_events(camera_id) WHERE ended_at_utc IS NULL
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_type
                ON track_events(event_type)
            """)
            conn.commit()
        logger.info("event_db_initialized", extra={"path": str(self.db_path)})

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a persistent connection for the current thread."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path, timeout=30.0, check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA busy_timeout=30000")
        return self._local.conn

    @contextmanager
    def _connect(self):
        conn = self._get_connection()
        try:
            yield conn
        except Exception:
            # On error, reset connection for this thread
            if hasattr(self._local, "conn"):
                try:
                    self._local.conn.close()
                except Exception:
                    pass
                self._local.conn = None
            raise

    def create_track_event(
        self,
        event_id: str,
        track_id: str,
        track_session_id: str,
        camera_id: str,
        started_at_utc: str,
        max_confidence: float,
        metadata: dict[str, Any],
    ) -> str:
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO track_events (
                        event_id, track_id, track_session_id, camera_id,
                        event_type, object_class, started_at_utc,
                        max_confidence, avg_confidence,
                        metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        track_id,
                        track_session_id,
                        camera_id,
                        "PERSON_TRACK",
                        "person",
                        started_at_utc,
                        max_confidence,
                        max_confidence,
                        json.dumps(metadata),
                        now,
                        now,
                    ),
                )
                conn.commit()
        logger.info("track_event_created", extra={"event_id": event_id, "track_id": track_id, "camera_id": camera_id})
        return event_id

    def update_track_event(
        self,
        event_id: str,
        ended_at_utc: str | None = None,
        duration_seconds: float | None = None,
        avg_confidence: float | None = None,
        clip_path: str | None = None,
        clip_recorded: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            with self._connect() as conn:
                recorded_val = int(clip_recorded) if clip_recorded is not None else None
                meta_json = json.dumps(metadata) if metadata is not None else None
                cursor = conn.execute(
                    """
                    UPDATE track_events
                    SET ended_at_utc = COALESCE(?, ended_at_utc),
                        duration_seconds = COALESCE(?, duration_seconds),
                        avg_confidence = COALESCE(?, avg_confidence),
                        clip_path = COALESCE(?, clip_path),
                        clip_recorded = COALESCE(?, clip_recorded),
                        metadata = COALESCE(?, metadata),
                        updated_at = ?
                    WHERE event_id = ?
                    """,
                    (
                        ended_at_utc,
                        duration_seconds,
                        avg_confidence,
                        clip_path,
                        recorded_val,
                        meta_json,
                        time.time(),
                        event_id,
                    ),
                )
                conn.commit()
                return cursor.rowcount > 0

    def get_event(self, event_id: str) -> TrackEvent | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM track_events WHERE event_id = ?", (event_id,)
                ).fetchone()
                return TrackEvent.from_row(row) if row else None

    def get_event_by_track(
        self, track_id: str, track_session_id: str | None = None
    ) -> TrackEvent | None:
        with self._lock:
            with self._connect() as conn:
                if track_session_id is not None:
                    row = conn.execute(
                        """
                        SELECT * FROM track_events
                        WHERE track_id = ? AND track_session_id = ?
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (track_id, track_session_id),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT * FROM track_events
                        WHERE track_id = ?
                        ORDER BY created_at DESC LIMIT 1
                        """,
                        (track_id,),
                    ).fetchone()
                return TrackEvent.from_row(row) if row else None

    def query_events(
        self,
        camera_id: str | None = None,
        start_utc: str | None = None,
        end_utc: str | None = None,
        object_class: str | None = None,
        clip_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TrackEvent]:
        conditions = []
        params: list[Any] = []

        if camera_id:
            conditions.append("camera_id = ?")
            params.append(camera_id)
        if start_utc:
            conditions.append("started_at_utc >= ?")
            params.append(start_utc)
        if end_utc:
            conditions.append("started_at_utc <= ?")
            params.append(end_utc)
        if object_class:
            conditions.append("object_class = ?")
            params.append(object_class)
        if clip_only:
            conditions.append("clip_recorded = 1")

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT * FROM track_events
                    {where_clause}
                    ORDER BY started_at_utc DESC
                    LIMIT ? OFFSET ?
                    """,
                    params + [limit, offset],
                ).fetchall()
                return [TrackEvent.from_row(row) for row in rows]

    def get_active_events(self, camera_id: str | None = None) -> list[TrackEvent]:
        conditions = ["ended_at_utc IS NULL"]
        params: list[Any] = []
        if camera_id:
            conditions.append("camera_id = ?")
            params.append(camera_id)

        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"""
                    SELECT * FROM track_events
                    WHERE {' AND '.join(conditions)}
                    ORDER BY started_at_utc DESC
                    """,
                    params,
                ).fetchall()
                return [TrackEvent.from_row(row) for row in rows]

    def close_active_events(self) -> int:
        """Mark active events without end times as ended."""
        now = time.time()
        now_utc = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE track_events
                    SET ended_at_utc = ?,
                        duration_seconds = MAX(0.0, ? - created_at),
                        updated_at = ?
                    WHERE ended_at_utc IS NULL
                    """,
                    (now_utc, now, now),
                )
                conn.commit()
                return cursor.rowcount

    def cleanup_old_events(self, retention_days: int | None = None) -> int:
        if retention_days is None:
            retention_days = self.config.retention_days

        cutoff_timestamp = time.time() - (retention_days * 86400)
        cutoff_utc = datetime.fromtimestamp(cutoff_timestamp, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        deleted_count = 0
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT clip_path FROM track_events WHERE started_at_utc < ? AND clip_path IS NOT NULL",
                    (cutoff_utc,),
                ).fetchall()
                clip_paths = [row["clip_path"] for row in rows if row["clip_path"]]

                cursor = conn.execute(
                    "DELETE FROM track_events WHERE started_at_utc < ?",
                    (cutoff_utc,),
                )
                deleted_count = cursor.rowcount
                conn.commit()

        clips_dir = Path(self.config.clip_storage_dir)
        for clip_path in clip_paths:
            try:
                full_path = clips_dir.parent / clip_path
                if not full_path.exists():
                    full_path = clips_dir / clip_path
                if not full_path.exists():
                    matches = list(clips_dir.glob(f"**/{Path(clip_path).name}"))
                    if matches:
                        full_path = matches[0]
                if full_path.exists():
                    full_path.unlink()
            except Exception as exc:
                logger.warning("clip_delete_failed", extra={"path": clip_path, "reason": str(exc)})

        if deleted_count:
            logger.info("event_cleanup_completed", extra={"deleted": deleted_count, "retention_days": retention_days})
        return deleted_count

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                total = conn.execute("SELECT COUNT(*) as c FROM track_events").fetchone()["c"]
                active = conn.execute("SELECT COUNT(*) as c FROM track_events WHERE ended_at_utc IS NULL").fetchone()["c"]
                with_clips = conn.execute("SELECT COUNT(*) as c FROM track_events WHERE clip_recorded = 1").fetchone()["c"]
                by_camera = conn.execute(
                    "SELECT camera_id, COUNT(*) as c FROM track_events GROUP BY camera_id"
                ).fetchall()
                return {
                    "total_events": total,
                    "active_events": active,
                    "events_with_clips": with_clips,
                    "by_camera": {row["camera_id"]: row["c"] for row in by_camera},
                }

    def close_all_connections(self) -> None:
        """Close all thread-local connections. Call on shutdown."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None