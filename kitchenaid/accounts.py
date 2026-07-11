"""Password hashing + account validation — the credential primitives behind username/password.

Pure stdlib (no dependency, in keeping with the zero-dep core): PBKDF2-HMAC-SHA256 with a random
per-user salt and a high iteration count (OWASP guidance), encoded in a self-describing string so
the parameters travel with the hash. Verification is constant-time. Passwords are never stored or
logged in plaintext; only the derived hash is persisted.

The store owns *where* users live (Postgres / files); this module owns *how* a password is
protected and *what* a valid username/password looks like.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 600_000          # OWASP 2023 floor for PBKDF2-HMAC-SHA256
_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,40}$")
_MIN_PASSWORD = 8


class AccountError(Exception):
    """Base class for registration/login problems."""


class DuplicateUser(AccountError):
    """That username is already taken."""


class BadCredentials(AccountError):
    """Unknown username or wrong password (deliberately indistinguishable)."""


def validate_username(username: str) -> str:
    if not isinstance(username, str) or not _USERNAME_RE.match(username):
        raise ValueError("username must be 3–40 chars: letters, digits, dot, dash, underscore")
    return username


def validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < _MIN_PASSWORD:
        raise ValueError(f"password must be at least {_MIN_PASSWORD} characters")
    return password


def hash_password(password: str, *, salt: "bytes | None" = None, iterations: int = _ITERATIONS) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of `password` against a stored hash string. False on any malformation."""
    try:
        algo, iterations, salt_b64, hash_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False
