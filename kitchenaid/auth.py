"""Bearer-token auth (opt-in) — the request-identity boundary.

When `KITCHENAID_AUTH_SECRET` is set, the API requires a signed token and derives the user's
identity **from the token**, never from client-supplied input (body/path `user_id`). When it's
unset (dev), the API is open and identity comes from the request, exactly as before. This
mirrors `DATABASE_URL`: production turns it on with one env var.

The token is a minimal HS256 JWT implemented on the stdlib (no dependency, in keeping with the
zero-dep core). The algorithm is fixed at verify time and the header's `alg` is never trusted,
so alg-confusion / `none` attacks don't apply. Signature comparison is constant-time.

Issuing tokens behind real credentials (OAuth / SSO / password) is the deployment's job — this
module owns the boundary every request crosses (`user_from_token` must hold). For dev/testing:
    KITCHENAID_AUTH_SECRET=... python -m kitchenaid.auth <user_id>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

_ALG = "HS256"


class AuthError(Exception):
    """A token was missing, malformed, expired, or had a bad signature."""


def auth_secret() -> Optional[str]:
    """The configured signing secret, or None. Read live so it can be toggled at runtime."""
    return os.environ.get("KITCHENAID_AUTH_SECRET") or None


def enabled() -> bool:
    return auth_secret() is not None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(user_id: str, *, secret: Optional[str] = None, ttl_seconds: int = 86400) -> str:
    """Mint a signed token for `user_id`. Raises if no secret is configured."""
    secret = secret or auth_secret()
    if not secret:
        raise RuntimeError("KITCHENAID_AUTH_SECRET is not set — cannot issue tokens")
    now = int(time.time())
    header = {"alg": _ALG, "typ": "JWT"}
    payload = {"sub": user_id, "iat": now, "exp": now + ttl_seconds}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode())
                     + "." + _b64url(json.dumps(payload, separators=(",", ":")).encode()))
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


def user_from_token(token: str, *, secret: Optional[str] = None) -> str:
    """Verify a token and return its subject (user_id). Raises AuthError on any problem.
    Fixed-algorithm HS256 with a constant-time signature check; the header alg is ignored."""
    secret = secret or auth_secret()
    if not secret:
        raise RuntimeError("KITCHENAID_AUTH_SECRET is not set — cannot verify tokens")
    try:
        signing_input, sig_b64 = token.rsplit(".", 1)
        expected = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        good_sig = hmac.compare_digest(expected, _b64url_decode(sig_b64))
        _, payload_b64 = signing_input.split(".")
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as e:  # malformed structure/base64/json
        raise AuthError(f"malformed token ({type(e).__name__})")
    if not good_sig:
        raise AuthError("bad signature")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthError("token expired")
    sub = payload.get("sub")
    if not sub:
        raise AuthError("token missing subject")
    return str(sub)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: KITCHENAID_AUTH_SECRET=... python -m kitchenaid.auth <user_id>")
        raise SystemExit(2)
    print(create_token(sys.argv[1]))
