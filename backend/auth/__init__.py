"""Authentication data layer for AIVISRA StreamCore.

Public surface:

- :mod:`backend.auth.passwords` — scrypt hashing and the 3-15 character policy.
- :mod:`backend.auth.users` — user CRUD, credential verification, first-admin setup.
- :mod:`backend.auth.sessions` — opaque server-side sessions.
- :mod:`backend.auth.audit` — append-only audit trail.

All use the central SQLite database at ``backend/database.db``.
"""

from .audit import AuditLog, get_audit_log, set_audit_log
from .passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    validate_password,
    verify_password,
)
from .sessions import (
    SESSION_COOKIE_NAME,
    SessionStore,
    get_session_store,
    hash_token,
    set_session_store,
)
from .users import (
    DEFAULT_ROLE,
    ROLES,
    UserStore,
    get_user_store,
    public_user,
    set_user_store,
)

__all__ = [
    "DEFAULT_ROLE",
    "MAX_PASSWORD_LENGTH",
    "MIN_PASSWORD_LENGTH",
    "PasswordPolicyError",
    "ROLES",
    "SESSION_COOKIE_NAME",
    "AuditLog",
    "SessionStore",
    "UserStore",
    "get_audit_log",
    "get_session_store",
    "get_user_store",
    "hash_password",
    "hash_token",
    "needs_rehash",
    "public_user",
    "set_audit_log",
    "set_session_store",
    "set_user_store",
    "validate_password",
    "verify_password",
]
