"""Server-side session repository.

Sessions are opaque bearer tokens. Only the SHA-256 of the token is stored, so
a leaked database cannot be replayed as a live cookie. The raw token is handed
to the caller once (for the ``HttpOnly`` cookie) and never persisted.

Sessions do not expire. Logout deletes the session row, so the database only
stores the session identity and observability fields.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..database import connect, get_db_path, init_db
from .users import PUBLIC_USER_FIELDS

SESSION_COOKIE_NAME = "aivisra_session"
SESSION_TOKEN_BYTES = 32

_SESSION_SELECT = """
SELECT
    s.session_id,
    s.user_id,
    s.created_at  AS session_created_at,
    s.last_seen_at,
    s.ip,
    s.user_agent,
    u.username,
    u.display_name,
    u.role,
    u.is_active,
    u.last_login_at,
    u.created_at  AS user_created_at,
    u.updated_at  AS user_updated_at
FROM sessions AS s
JOIN users AS u ON u.user_id = s.user_id
"""


def hash_token(token: str) -> str:
    """Return the stored form of an opaque session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "created_at": row["session_created_at"],
        "last_seen_at": row["last_seen_at"],
        "ip": row["ip"],
        "user_agent": row["user_agent"],
    }


def _user_dict(row: sqlite3.Row) -> dict[str, Any]:
    user = {
        "user_id": row["user_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "last_login_at": row["last_login_at"],
        "created_at": row["user_created_at"],
        "updated_at": row["user_updated_at"],
    }
    # Keep the field order in sync with users.PUBLIC_USER_FIELDS.
    return {field: user[field] for field in PUBLIC_USER_FIELDS}


class SessionStore:
    """Create, resolve, touch and revoke sessions in the central database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser().resolve() if db_path else get_db_path()
        init_db(self.db_path)

    # ------------------------------------------------------------------ create
    def create_session(
        self, user_id: str, *, ip: str | None = None, user_agent: str | None = None
    ) -> tuple[str, dict[str, Any]]:
        """Create a session and return ``(raw_token, session)``.

        ``raw_token`` is the only time the token is visible; store it in an
        ``HttpOnly`` cookie. ``session["session_id"]`` is its hash.
        """
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        session_id = hash_token(token)
        now = time.time()

        try:
            with connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO sessions
                        (session_id, user_id, created_at, last_seen_at, ip, user_agent)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, user_id, now, now, ip, user_agent),
                )
        except sqlite3.IntegrityError as exc:
            raise KeyError(f"Unknown user_id: {user_id}") from exc

        session = {
            "session_id": session_id,
            "user_id": user_id,
            "created_at": now,
            "last_seen_at": now,
            "ip": ip,
            "user_agent": user_agent,
        }
        return token, session

    # ------------------------------------------------------------------- read
    def resolve_session(self, token: str, *, touch: bool = True) -> dict[str, Any] | None:
        """Return ``{"session": ..., "user": ...}`` for a token, else ``None``."""
        if not token:
            return None
        session_id = hash_token(token)

        with connect(self.db_path) as conn:
            row = conn.execute(_SESSION_SELECT + " WHERE s.session_id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            if touch:
                now = time.time()
                conn.execute(
                    "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?",
                    (now, session_id),
                )
                row = conn.execute(
                    _SESSION_SELECT + " WHERE s.session_id = ?", (session_id,)
                ).fetchone()

        return {"session": _session_dict(row), "user": _user_dict(row)}

    def list_sessions(
        self, user_id: str, *, include_revoked: bool = False
    ) -> list[dict[str, Any]]:
        sql = _SESSION_SELECT + " WHERE s.user_id = ?"
        sql += " ORDER BY s.created_at DESC"
        with connect(self.db_path) as conn:
            rows = conn.execute(sql, (user_id,)).fetchall()
        return [_session_dict(row) for row in rows]

    # ------------------------------------------------------------------ touch
    def touch_session(self, session_id: str) -> bool:
        """Update ``last_seen_at`` for a stored session id (the hash)."""
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?",
                (time.time(), session_id),
            )
        return cursor.rowcount > 0

    # ----------------------------------------------------------------- revoke
    def revoke_session(self, session_id: str) -> bool:
        """Delete by stored session id (the hash)."""
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
        return cursor.rowcount > 0

    def revoke_token(self, token: str) -> bool:
        """Revoke by raw cookie token."""
        if not token:
            return False
        return self.revoke_session(hash_token(token))

    def revoke_all_for_user(self, user_id: str) -> int:
        """Delete every session for a user. Returns the number deleted."""
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE user_id = ?",
                (user_id,),
            )
        return cursor.rowcount

_SESSION_STORE: SessionStore | None = None
_SESSION_STORE_LOCK = threading.Lock()


def get_session_store() -> SessionStore:
    """Return the process-wide session store (created on first use)."""
    global _SESSION_STORE
    if _SESSION_STORE is None:
        with _SESSION_STORE_LOCK:
            if _SESSION_STORE is None:
                _SESSION_STORE = SessionStore()
    return _SESSION_STORE


def set_session_store(store: SessionStore | None) -> None:
    """Replace the singleton (used by tests)."""
    global _SESSION_STORE
    with _SESSION_STORE_LOCK:
        _SESSION_STORE = store
