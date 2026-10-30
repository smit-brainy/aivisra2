"""Append-only audit trail for security-relevant actions.

Rows live in ``audit_log`` in the central ``backend/database.db``. The table is
intentionally independent of ``users`` (no foreign key) so entries survive user
deletion and keep the original ``user_id``.

Callers record at the API layer, e.g.::

    audit.record(
        "auth.login.failed",
        resource="auth/login",
        detail={"username": "alice"},
        ip=request.client.host,
    )

Actions use dotted names: ``auth.login``, ``auth.logout``, ``user.create``,
``user.update``, ``user.delete``, ``camera.update``, ``area.create``, ...
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..database import connect, get_db_path, init_db

AUDIT_FIELDS = (
    "id",
    "user_id",
    "action",
    "resource",
    "detail",
    "ip",
    "created_at",
)


def _encode_detail(detail: Any) -> str | None:
    if detail is None:
        return None
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, separators=(",", ":"), sort_keys=True, default=str)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {field: row[field] for field in AUDIT_FIELDS}


class AuditLog:
    """Write and query audit entries."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser().resolve() if db_path else get_db_path()
        init_db(self.db_path)

    def record(
        self,
        action: str,
        *,
        user_id: str | None = None,
        resource: str | None = None,
        detail: Any = None,
        ip: str | None = None,
    ) -> dict[str, Any]:
        """Append one entry and return it."""
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action is required")
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_log (user_id, action, resource, detail, ip, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    action.strip(),
                    resource,
                    _encode_detail(detail),
                    ip,
                    time.time(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM audit_log WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return _row_to_dict(row)

    def list_entries(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        user_id: str | None = None,
        since: float | None = None,
    ) -> list[dict[str, Any]]:
        """Newest-first entries, optionally filtered."""
        where: list[str] = []
        params: list[Any] = []
        if action:
            where.append("action = ?")
            params.append(action)
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if since is not None:
            where.append("created_at >= ?")
            params.append(float(since))

        sql = "SELECT * FROM audit_log"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([max(0, int(limit)), max(0, int(offset))])

        with connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def count_entries(
        self,
        *,
        action: str | None = None,
        user_id: str | None = None,
        since: float | None = None,
    ) -> int:
        where: list[str] = []
        params: list[Any] = []
        if action:
            where.append("action = ?")
            params.append(action)
        if user_id:
            where.append("user_id = ?")
            params.append(user_id)
        if since is not None:
            where.append("created_at >= ?")
            params.append(float(since))

        sql = "SELECT COUNT(*) AS c FROM audit_log"
        if where:
            sql += " WHERE " + " AND ".join(where)
        with connect(self.db_path) as conn:
            return int(conn.execute(sql, params).fetchone()["c"])


_AUDIT_LOG: AuditLog | None = None
_AUDIT_LOG_LOCK = threading.Lock()


def get_audit_log() -> AuditLog:
    """Return the process-wide audit log (created on first use)."""
    global _AUDIT_LOG
    if _AUDIT_LOG is None:
        with _AUDIT_LOG_LOCK:
            if _AUDIT_LOG is None:
                _AUDIT_LOG = AuditLog()
    return _AUDIT_LOG


def set_audit_log(log: AuditLog | None) -> None:
    """Replace the singleton (used by tests)."""
    global _AUDIT_LOG
    with _AUDIT_LOG_LOCK:
        _AUDIT_LOG = log
