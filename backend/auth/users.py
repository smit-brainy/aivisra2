"""User repository backed by the central ``backend/database.db``.

A user row holds the credential hash and the RBAC role. Passwords are never
returned by public methods; use :meth:`UserStore.verify_credentials` for login.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..database import connect, get_db_path, init_db
from .passwords import hash_password, validate_password, verify_password

ROLES = ("admin", "operator", "viewer")
DEFAULT_ROLE = "operator"

# Columns safe to hand to API callers (never ``password_hash``).
PUBLIC_USER_FIELDS = (
    "user_id",
    "username",
    "display_name",
    "role",
    "is_active",
    "last_login_at",
    "created_at",
    "updated_at",
)

_dummy_lock = threading.Lock()
_dummy_hash: str | None = None


def public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    """Project a user row onto the public fields, with booleans normalised."""
    user = {field: row[field] for field in PUBLIC_USER_FIELDS}
    user["is_active"] = bool(user["is_active"])
    return user


def _dummy_password_hash() -> str:
    """A valid hash used to equalise timing when a username does not exist."""
    global _dummy_hash
    if _dummy_hash is None:
        with _dummy_lock:
            if _dummy_hash is None:
                _dummy_hash = hash_password(uuid.uuid4().hex[:15])
    return _dummy_hash


def _clean_username(username: str) -> str:
    if not isinstance(username, str):
        raise ValueError("username must be a string")
    clean = username.strip()
    if not clean:
        raise ValueError("username is required")
    return clean


def _validate_role(role: str) -> str:
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    return role


class UserStore:
    """Thread-safe CRUD for the ``users`` table."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path).expanduser().resolve() if db_path else get_db_path()
        init_db(self.db_path)

    # ------------------------------------------------------------------ create
    def _insert_user(
        self,
        conn: sqlite3.Connection,
        *,
        username: str,
        password: str,
        display_name: str | None,
        role: str,
        is_active: bool,
        user_id: str | None = None,
    ) -> sqlite3.Row:
        clean_username = _clean_username(username)
        validate_password(password)
        _validate_role(role)

        uid = user_id or uuid.uuid4().hex
        name = (display_name or "").strip() or clean_username
        now = time.time()
        conn.execute(
            """
            INSERT INTO users
                (user_id, username, display_name, password_hash, role,
                 is_active, last_login_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                uid,
                clean_username,
                name,
                hash_password(password),
                role,
                1 if is_active else 0,
                now,
                now,
            ),
        )
        return conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,)).fetchone()

    def create_user(
        self,
        username: str,
        password: str,
        *,
        display_name: str | None = None,
        role: str = DEFAULT_ROLE,
        is_active: bool = True,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Insert a user and return its public representation."""
        clean_username = _clean_username(username)
        validate_password(password)
        _validate_role(role)
        try:
            with connect(self.db_path) as conn:
                row = self._insert_user(
                    conn,
                    username=clean_username,
                    password=password,
                    display_name=display_name,
                    role=role,
                    is_active=is_active,
                    user_id=user_id,
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Username '{clean_username}' already exists") from exc
        return public_user(row)

    def has_any_users(self) -> bool:
        """True once at least one account exists (i.e. setup is complete)."""
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None

    def create_first_admin(
        self,
        username: str,
        password: str,
        *,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """Create the bootstrap administrator, only while ``users`` is empty.

        Backs the first-run setup screen. The check and insert happen in one
        ``BEGIN IMMEDIATE`` transaction so two concurrent setup requests cannot
        both create an admin. Raises ``ValueError`` if setup is already done.
        """
        clean_username = _clean_username(username)
        validate_password(password)
        try:
            with connect(self.db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None:
                    raise ValueError("Setup has already been completed")
                row = self._insert_user(
                    conn,
                    username=clean_username,
                    password=password,
                    display_name=display_name,
                    role="admin",
                    is_active=True,
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Username '{clean_username}' already exists") from exc
        return public_user(row)

    # -------------------------------------------------------------------- read
    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return public_user(row) if row else None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        clean = _clean_username(username)
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (clean,)
            ).fetchone()
        return public_user(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY username COLLATE NOCASE ASC"
            ).fetchall()
        return [public_user(row) for row in rows]

    def count_active_admins(self) -> int:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM users "
                "WHERE role = 'admin' AND is_active = 1"
            ).fetchone()
        return int(row["c"])

    # ------------------------------------------------------------------ update
    def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        """Apply a partial update. Raises ``KeyError`` when the user is missing."""
        fields: dict[str, Any] = {}
        if display_name is not None:
            name = display_name.strip()
            if not name:
                raise ValueError("display_name cannot be empty")
            fields["display_name"] = name
        if role is not None:
            fields["role"] = _validate_role(role)
        if is_active is not None:
            fields["is_active"] = 1 if is_active else 0

        if not fields:
            user = self.get_user(user_id)
            if user is None:
                raise KeyError(user_id)
            return user

        assignments = ", ".join(f"{key} = ?" for key in fields)
        params = list(fields.values()) + [time.time(), user_id]
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE users SET {assignments}, updated_at = ? WHERE user_id = ?",
                params,
            )
            if cursor.rowcount == 0:
                raise KeyError(user_id)
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return public_user(row)

    def set_password(self, user_id: str, password: str) -> None:
        """Replace a user's password (policy-checked)."""
        validate_password(password)
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE user_id = ?",
                (hash_password(password), time.time(), user_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(user_id)

    def record_login(self, user_id: str) -> dict[str, Any]:
        """Stamp ``last_login_at`` after a successful sign-in."""
        now = time.time()
        with connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE users SET last_login_at = ?, updated_at = ? WHERE user_id = ?",
                (now, now, user_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(user_id)
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return public_user(row)

    def delete_user(self, user_id: str) -> bool:
        """Delete a user; their sessions cascade away. Returns whether a row went."""
        with connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        return cursor.rowcount > 0

    # ------------------------------------------------------------------- login
    def verify_credentials(self, username: str, password: str) -> dict[str, Any] | None:
        """Return the public user when the password matches, else ``None``.

        Inactive users are returned too (with ``is_active == False``) so the
        API layer can distinguish "disabled" from "bad credentials" if it wants
        to. Unknown usernames still run a dummy hash to keep timing uniform.
        """
        try:
            clean = _clean_username(username)
        except ValueError:
            clean = ""

        if not clean:
            verify_password(password, _dummy_password_hash())
            return None

        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (clean,)
            ).fetchone()

        if row is None:
            verify_password(password, _dummy_password_hash())
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return public_user(row)


_USER_STORE: UserStore | None = None
_USER_STORE_LOCK = threading.Lock()


def get_user_store() -> UserStore:
    """Return the process-wide user store (created on first use)."""
    global _USER_STORE
    if _USER_STORE is None:
        with _USER_STORE_LOCK:
            if _USER_STORE is None:
                _USER_STORE = UserStore()
    return _USER_STORE


def set_user_store(store: UserStore | None) -> None:
    """Replace the singleton (used by tests)."""
    global _USER_STORE
    with _USER_STORE_LOCK:
        _USER_STORE = store
