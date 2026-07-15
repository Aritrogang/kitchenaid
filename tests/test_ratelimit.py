"""Rate-limiting tests — the sliding-window limiter and the API's 429 behavior.

Standalone (limiter unit tests only):  python3 tests/test_ratelimit.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.ratelimit import RateLimiter  # noqa: E402


# --- the limiter ---------------------------------------------------------------------

def test_allows_up_to_limit_then_blocks():
    rl = RateLimiter(max_requests=3, window_seconds=60)
    assert all(rl.check("k", now=1000.0)[0] for _ in range(3))
    allowed, retry = rl.check("k", now=1000.0)
    assert allowed is False and 0 < retry <= 60


def test_window_slides():
    rl = RateLimiter(max_requests=1, window_seconds=10)
    assert rl.check("k", now=100.0)[0] is True
    assert rl.check("k", now=105.0)[0] is False        # still inside the 10s window
    assert rl.check("k", now=111.0)[0] is True         # window has passed


def test_keys_are_independent():
    rl = RateLimiter(max_requests=1, window_seconds=60)
    assert rl.check("a", now=1.0)[0] is True
    assert rl.check("b", now=1.0)[0] is True            # different key, its own budget
    assert rl.check("a", now=1.0)[0] is False


def test_zero_or_negative_disables():
    rl = RateLimiter(max_requests=0)
    assert rl.enabled is False
    assert all(rl.check("k")[0] for _ in range(100))


# --- API integration -----------------------------------------------------------------

def test_api_returns_429_over_the_chat_limit(monkeypatch):
    monkeypatch.setenv("KITCHENAID_RATE_CHAT_PER_MIN", "2")     # tiny limit for the test
    monkeypatch.delenv("KITCHENAID_AUTH_SECRET", raising=False)  # open mode -> keyed by IP
    from fastapi.testclient import TestClient
    from kitchenaid.api import create_app

    client = TestClient(create_app())                           # fresh app -> fresh limiter
    body = {"user_id": "rl", "query": "quick dinner",
            "profile": {"user_id": "rl", "allergies": [], "diet": "none"}}
    assert client.post("/chat", json=body).status_code == 200
    assert client.post("/chat", json=body).status_code == 200
    blocked = client.post("/chat", json=body)                   # 3rd within the window
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}
    # a cheap endpoint is never rate limited (the web client polls it)
    assert client.get("/health").status_code == 200


def _run_standalone():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn) and "monkeypatch" not in fn.__code__.co_varnames:
            fn()
            print(f"  ok  {name}")
    print("limiter unit tests passed (run pytest for the API 429 test).")


if __name__ == "__main__":
    _run_standalone()
