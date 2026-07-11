"""Auth tests — the request-identity boundary.

Covers the token primitive (sign / verify / expiry / tamper / wrong-secret) and the API:
with no secret it's open (dev, unchanged); with a secret it takes identity from the token and
refuses to let one user read or write another's data — the safety gate still holds either way.

Standalone needs pytest (monkeypatch/raises):  python3 -m pytest tests/test_auth.py
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import auth  # noqa: E402
from kitchenaid.auth import AuthError, create_token, user_from_token  # noqa: E402

SECRET = "test-secret-123"
OMNIVORE = {"allergies": [], "diet": "none", "budget_per_meal_usd": 8.0, "name": "U"}
PEANUT = {"allergies": ["peanut"], "diet": "vegetarian", "name": "U"}


# --- token primitive -----------------------------------------------------------------

def test_token_round_trips():
    assert user_from_token(create_token("alice", secret=SECRET), secret=SECRET) == "alice"


def test_expired_token_rejected():
    with pytest.raises(AuthError):
        user_from_token(create_token("alice", secret=SECRET, ttl_seconds=-1), secret=SECRET)


def test_wrong_secret_rejected():
    with pytest.raises(AuthError):
        user_from_token(create_token("alice", secret=SECRET), secret="other-secret")


def test_tampered_payload_rejected():
    head, _payload, sig = create_token("alice", secret=SECRET).split(".")
    forged_payload = create_token("bob", secret="unrelated").split(".")[1]   # a different sub
    with pytest.raises(AuthError):
        user_from_token(".".join([head, forged_payload, sig]), secret=SECRET)


def test_enabled_reflects_env(monkeypatch):
    monkeypatch.delenv("KITCHENAID_AUTH_SECRET", raising=False)
    assert auth.enabled() is False
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    assert auth.enabled() is True


# --- API: auth OFF (open, dev) — unchanged behavior ----------------------------------

def test_api_open_when_no_secret(monkeypatch):
    monkeypatch.delenv("KITCHENAID_AUTH_SECRET", raising=False)
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    assert client.get("/health").json()["auth"] is False
    u = f"open-{uuid.uuid4()}"
    r = client.post("/chat", json={"user_id": u, "query": "quick dinner",
                                   "profile": {**OMNIVORE, "user_id": u}})
    assert r.status_code == 200 and r.json()["meal"] is not None


# --- API: auth ON --------------------------------------------------------------------

def test_api_requires_token_when_secret_set(monkeypatch):
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    assert client.get("/health").json()["auth"] is True
    assert client.post("/chat", json={"user_id": "x", "query": "quick dinner"}).status_code == 401
    assert client.get("/profile/x", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_api_uses_token_identity_and_isolates_users(monkeypatch):
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    alice, bob = f"alice-{uuid.uuid4()}", f"bob-{uuid.uuid4()}"
    atok = {"Authorization": f"Bearer {create_token(alice, secret=SECRET)}"}

    assert client.put(f"/profile/{alice}", headers=atok, json={**PEANUT}).status_code == 200
    # alice cannot read or write bob's data
    assert client.put(f"/profile/{bob}", headers=atok, json={**OMNIVORE}).status_code == 403
    assert client.get(f"/profile/{bob}", headers=atok).status_code == 403

    # chat with alice's token but a spoofed body user_id -> token identity wins, peanut still gated
    r = client.post("/chat", headers=atok, json={"user_id": bob, "query": "noodles please"})
    assert r.status_code == 200
    meal = r.json()["meal"]
    if meal:
        assert not any("peanut" in i["item"].lower() for i in meal["ingredients"])
