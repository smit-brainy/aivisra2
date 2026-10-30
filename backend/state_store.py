"""Persistent UI-editable metadata (camera names, areas, settings).

The StreamCore pipeline configuration stays in ``app.yaml``. This store only
holds metadata that operators can edit at runtime. All application tables,
including auth tables, live in the central database at ``backend/database.db``
(see :mod:`backend.database`), which keeps the project path-agnostic.

Override the location with ``STREAMCORE_DB`` when running tests.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .database import connect as _db_connect
from .database import get_db_path, init_db, resolve_db_path

CAMERA_KINDS = ("person", "vehicle", "both")
CAMERA_LEVELS = ("standard", "enhanced", "off")

__all__ = [
    "CAMERA_KINDS",
    "CAMERA_LEVELS",
    "StateStore",
    "get_state_store",
    "resolve_db_path",
    "set_state_store",
]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


class StateStore:
    """Thread-safe SQLite store for operator-editable metadata."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser().resolve() if db_path else get_db_path()
        init_db(self.db_path)
        self._lock = threading.RLock()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with _db_connect(self.db_path) as conn:
            yield conn

    # ------------------------------------------------------------------ cameras
    def ensure_camera(self, camera_id: str, display_name: str | None = None) -> dict[str, Any]:
        """Create the metadata row for a configured camera if it does not exist."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM camera_metadata WHERE camera_id = ?", (camera_id,)
            ).fetchone()
            if row is None:
                now = time.time()
                conn.execute(
                    """
                    INSERT INTO camera_metadata
                        (camera_id, display_name, area_id, kind, level, notes, created_at, updated_at)
                    VALUES (?, ?, NULL, 'both', 'standard', NULL, ?, ?)
                    """,
                    (camera_id, display_name or camera_id, now, now),
                )
                row = conn.execute(
                    "SELECT * FROM camera_metadata WHERE camera_id = ?", (camera_id,)
                ).fetchone()
        return _row_to_dict(row)

    def get_camera(self, camera_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM camera_metadata WHERE camera_id = ?", (camera_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list_cameras(self) -> dict[str, dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM camera_metadata").fetchall()
        return {row["camera_id"]: _row_to_dict(row) for row in rows}

    def update_camera(self, camera_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Apply a partial metadata update, creating the row when needed."""
        allowed = {"display_name", "area_id", "kind", "level", "notes"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unsupported camera fields: {', '.join(sorted(unknown))}")

        for key in ("display_name", "kind", "level"):
            if key in fields and fields[key] is None:
                raise ValueError(f"{key} cannot be null")
        if "kind" in fields and fields["kind"] not in CAMERA_KINDS:
            raise ValueError(f"kind must be one of {', '.join(CAMERA_KINDS)}")
        if "level" in fields and fields["level"] not in CAMERA_LEVELS:
            raise ValueError(f"level must be one of {', '.join(CAMERA_LEVELS)}")
        if "display_name" in fields and not str(fields["display_name"]).strip():
            raise ValueError("display_name cannot be empty")
        if "area_id" in fields and fields["area_id"] is not None:
            if not self.area_exists(fields["area_id"]):
                raise ValueError(f"Unknown area_id: {fields['area_id']}")

        if not fields:
            return self.ensure_camera(camera_id)
        now = time.time()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        params = [fields[key] for key in fields] + [now, camera_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE camera_metadata SET {assignments}, updated_at = ? WHERE camera_id = ?",
                params,
            )
            row = conn.execute(
                "SELECT * FROM camera_metadata WHERE camera_id = ?", (camera_id,)
            ).fetchone()
        return _row_to_dict(row)

    # -------------------------------------------------------------------- areas
    def area_exists(self, area_id: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT 1 FROM areas WHERE area_id = ?", (area_id,)).fetchone()
        return row is not None

    def list_areas(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM areas ORDER BY sort_order ASC, name COLLATE NOCASE ASC"
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def create_area(self, name: str, sort_order: int = 0) -> dict[str, Any]:
        clean = (name or "").strip()
        if not clean:
            raise ValueError("name is required")
        area_id = f"area-{uuid.uuid4().hex[:10]}"
        now = time.time()
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO areas (area_id, name, sort_order, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (area_id, clean, int(sort_order), now, now),
                )
                row = conn.execute("SELECT * FROM areas WHERE area_id = ?", (area_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"An area named '{clean}' already exists") from exc
        return _row_to_dict(row)

    def update_area(
        self,
        area_id: str,
        name: str | None = None,
        sort_order: int | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if name is not None:
            clean = name.strip()
            if not clean:
                raise ValueError("name cannot be empty")
            fields["name"] = clean
        if sort_order is not None:
            fields["sort_order"] = int(sort_order)
        if not fields:
            raise ValueError("Nothing to update")

        now = time.time()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        params = list(fields.values()) + [now, area_id]
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute(
                    f"UPDATE areas SET {assignments}, updated_at = ? WHERE area_id = ?",
                    params,
                )
                if cursor.rowcount == 0:
                    raise KeyError(area_id)
                row = conn.execute("SELECT * FROM areas WHERE area_id = ?", (area_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"An area named '{fields.get('name')}' already exists") from exc
        return _row_to_dict(row)

    def delete_area(self, area_id: str) -> bool:
        """Delete an area and unassign any cameras that referenced it."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE camera_metadata SET area_id = NULL, updated_at = ? WHERE area_id = ?",
                (time.time(), area_id),
            )
            cursor = conn.execute("DELETE FROM areas WHERE area_id = ?", (area_id,))
        return cursor.rowcount > 0

    # ----------------------------------------------------------------- settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, str(value), time.time()),
            )


_STORE: StateStore | None = None
_STORE_LOCK = threading.Lock()


def get_state_store() -> StateStore:
    """Return the process-wide metadata store (created on first use)."""
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = StateStore()
    return _STORE


def set_state_store(store: StateStore | None) -> None:
    """Replace the singleton (used by tests)."""
    global _STORE
    with _STORE_LOCK:
        _STORE = store
