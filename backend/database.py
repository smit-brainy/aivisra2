"""Central SQLite database for the AIVISRA backend.

Every application table lives in one file: ``backend/database.db``. The path is
derived from this module's own location, so the repository can be cloned to any
directory on any machine (Linux, Windows, CI, ...) and the database follows it.

Override the location with ``STREAMCORE_DB`` when running tests or when a
deployment keeps its data outside the repository. The older
``STREAMCORE_STATE_DB`` variable is still honoured for compatibility.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BACKEND_DIR = Path(__file__).resolve().parent
DB_FILENAME = "database.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS areas (
    area_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_areas_name
    ON areas (name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS camera_metadata (
    camera_id TEXT PRIMARY KEY,
    display_name TEXT,
    area_id TEXT,
    kind TEXT NOT NULL DEFAULT 'both',
    level TEXT NOT NULL DEFAULT 'standard',
    notes TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cameras (
    camera_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    uri TEXT NOT NULL,
    codec TEXT NOT NULL DEFAULT 'h264',
    decoder TEXT NOT NULL DEFAULT 'auto',
    decoding_fps REAL,
    status TEXT NOT NULL DEFAULT 'active',
    camera_metadata TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator'
        CHECK (role IN ('admin', 'operator', 'viewer')),
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),
    last_login_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
    ON users (username COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    ip TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    action TEXT NOT NULL,
    resource TEXT,
    detail TEXT,
    ip TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log (created_at);

CREATE TABLE IF NOT EXISTS inference_events (
    event_id TEXT PRIMARY KEY,
    track_id TEXT NOT NULL,
    track_session_id TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    camera_name TEXT,
    event_type TEXT NOT NULL,
    object_class TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    duration_seconds REAL,
    max_confidence REAL,
    avg_confidence REAL,
    description TEXT,
    snapshot_path TEXT,
    clip_path TEXT,
    clip_recorded INTEGER NOT NULL DEFAULT 0,
    metadata TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_inference_camera_time
    ON inference_events(camera_id, started_at_utc);
CREATE INDEX IF NOT EXISTS idx_inference_track
    ON inference_events(track_id, track_session_id);
CREATE INDEX IF NOT EXISTS idx_inference_active
    ON inference_events(camera_id) WHERE ended_at_utc IS NULL;
CREATE INDEX IF NOT EXISTS idx_inference_type
    ON inference_events(event_type);
"""

_db_path_lock = threading.Lock()
_db_path: Path | None = None


def resolve_db_path() -> Path:
    """Return the database path, honouring environment overrides."""
    override = os.environ.get("STREAMCORE_DB") or os.environ.get("STREAMCORE_STATE_DB")
    if override:
        return Path(override).expanduser().resolve()
    return BACKEND_DIR / DB_FILENAME


def get_db_path() -> Path:
    """Return the process-wide database path (resolved once)."""
    global _db_path
    if _db_path is None:
        with _db_path_lock:
            if _db_path is None:
                _db_path = resolve_db_path()
    return _db_path


def set_db_path(path: str | Path | None) -> None:
    """Override the process-wide database path (used by tests)."""
    global _db_path
    with _db_path_lock:
        _db_path = Path(path).expanduser().resolve() if path is not None else None


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a short-lived connection with the project's standard pragmas.

    Commits on success, rolls back on error, always closes. SQLite connections
    are cheap; opening one per operation keeps this safe across FastAPI worker
    threads without a connection pool.
    """
    path = Path(db_path).expanduser().resolve() if db_path is not None else get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path | None = None) -> Path:
    """Create every application table/index if missing. Idempotent."""
    path = Path(db_path).expanduser().resolve() if db_path is not None else get_db_path()
    with connect(path) as conn:
        conn.executescript(_SCHEMA)
        # Older builds stored ``expires_at`` and ``revoked``. Rebuild only
        # this table so existing users and audit history remain untouched.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        if {"expires_at", "revoked"}.issubset(columns):
            conn.executescript(
                """
                CREATE TABLE sessions_new (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    ip TEXT,
                    user_agent TEXT
                );
                INSERT INTO sessions_new
                    (session_id, user_id, created_at, last_seen_at, ip, user_agent)
                SELECT session_id, user_id, created_at, last_seen_at, ip, user_agent
                FROM sessions;
                DROP TABLE sessions;
                ALTER TABLE sessions_new RENAME TO sessions;
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
                """
            )
    return path
