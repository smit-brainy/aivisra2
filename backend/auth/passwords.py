"""Password hashing and policy for AIVISRA StreamCore.

Policy
------
Any password is accepted, including common/dictionary passwords. The only rule
is length: ``3 <= len(password) <= 15`` (counted in Unicode characters).

Storage format
--------------
Hashes are algorithm-tagged so parameters can change later without breaking
existing rows::

    scrypt$N$r$p$<salt_b64>$<hash_b64>

Only the Python standard library is used (``hashlib.scrypt``); no extra
dependency is required.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

MIN_PASSWORD_LENGTH = 3
MAX_PASSWORD_LENGTH = 15

ALGORITHM = "scrypt"

# Cost parameters. 128 * N * r = 16 MiB of memory per hash.
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32
_SALT_BYTES = 16
_MAXMEM = 64 * 1024 * 1024  # headroom over the 16 MiB the parameters need


class PasswordPolicyError(ValueError):
    """Raised when a password fails the length policy."""


def validate_password(password: str) -> str:
    """Return ``password`` if it satisfies the policy, else raise.

    Any characters are allowed; only the length is checked.
    """
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string")
    length = len(password)
    if length < MIN_PASSWORD_LENGTH or length > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be between {MIN_PASSWORD_LENGTH} and "
            f"{MAX_PASSWORD_LENGTH} characters"
        )
    return password


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=dklen,
        maxmem=_MAXMEM,
    )


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt.

    Raises :class:`PasswordPolicyError` when the length policy fails.
    """
    validate_password(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _scrypt(password, salt, _N, _R, _P, _DKLEN)
    return f"{ALGORITHM}${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Check ``password`` against a stored hash.

    Returns ``False`` for malformed or missing hashes instead of raising, so
    callers can treat every failure as a normal authentication miss.
    """
    if not isinstance(password, str) or not password or not stored_hash:
        return False
    try:
        algorithm, n_raw, r_raw, p_raw, salt_b64, digest_b64 = stored_hash.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = _unb64(salt_b64)
        expected = _unb64(digest_b64)
        candidate = _scrypt(password, salt, int(n_raw), int(r_raw), int(p_raw), len(expected))
    except Exception:
        return False
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored_hash: str | None) -> bool:
    """True when a stored hash uses different parameters than the current ones."""
    if not stored_hash:
        return True
    try:
        algorithm, n_raw, r_raw, p_raw, _salt, _digest = stored_hash.split("$")
        params = (algorithm, int(n_raw), int(r_raw), int(p_raw))
    except (TypeError, ValueError):
        return True
    return params != (ALGORITHM, _N, _R, _P)
