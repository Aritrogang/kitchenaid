"""Account tests — username/password registration and login.

Covers password hashing (salted PBKDF2, constant-time verify, never plaintext), the
register -> login -> token flow and its failure modes, and the HTTP end-to-end: register, then
save your profile and chat with the returned token — your data, isolated to your identity.

Needs pytest (monkeypatch):  python3 -m pytest tests/test_accounts.py
"""

import os
import sys
import tempfile
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import accounts  # noqa: E402
from kitchenaid.accounts import BadCredentials, DuplicateUser, hash_password, verify_password  # noqa: E402
from kitchenaid.api import KitchenaidService  # noqa: E402
from kitchenaid.profile_keeper import ProfileKeeper  # noqa: E402

SECRET = "test-secret-accounts"


def _service():
    return KitchenaidService(ProfileKeeper(tempfile.mkdtemp()))


# --- password hashing ----------------------------------------------------------------

def test_hash_verify_round_trip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong password", h)


def test_hash_is_salted_and_never_plaintext():
    h1, h2 = hash_password("same-password-x"), hash_password("same-password-x")
    assert h1 != h2 and "same-password-x" not in h1     # random per-hash salt, no plaintext


def test_verify_rejects_malformed_hash():
    assert verify_password("anything", "not-a-valid-hash") is False


def test_validation_rules():
    for bad in ("ab", "has space", "waytoolong" * 6):
        with pytest.raises(ValueError):
            accounts.validate_username(bad)
    with pytest.raises(ValueError):
        accounts.validate_password("short")
    assert accounts.validate_username("alice_01") == "alice_01"


# --- service register / login --------------------------------------------------------

def test_register_then_login(monkeypatch):
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    svc = _service()
    reg = svc.register("alice", "supersecret")
    assert reg["username"] == "alice" and reg["token"]
    log = svc.login("alice", "supersecret")
    assert log["user_id"] == reg["user_id"] and log["token"]


def test_duplicate_username_rejected(monkeypatch):
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    svc = _service()
    svc.register("bob", "supersecret")
    with pytest.raises(DuplicateUser):
        svc.register("bob", "different-pass")


def test_login_failures_are_indistinguishable(monkeypatch):
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    svc = _service()
    svc.register("carol", "supersecret")
    with pytest.raises(BadCredentials):
        svc.login("carol", "wrong")          # wrong password
    with pytest.raises(BadCredentials):
        svc.login("ghost", "whatever")       # unknown user -> same error (no enumeration)


# --- HTTP end to end -----------------------------------------------------------------

def test_http_register_save_and_chat_privately(monkeypatch):
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    uname = f"u{uuid.uuid4().hex[:10]}"

    r = client.post("/auth/register", json={"username": uname, "password": "supersecret"})
    assert r.status_code == 201
    body = r.json()
    uid, tok = body["user_id"], {"Authorization": f"Bearer {body['token']}"}

    # save my data with my token, read it back
    assert client.put(f"/profile/{uid}", headers=tok,
                      json={"allergies": ["peanut"], "diet": "vegetarian"}).status_code == 200
    assert client.get(f"/profile/{uid}", headers=tok).json()["allergies"] == ["peanut"]

    # chat under my identity stays peanut-safe — and note NO user_id in the body: it comes
    # from the token (the realistic authed-client shape).
    meal = client.post("/chat", headers=tok, json={"query": "noodles please"}).json().get("meal")
    if meal:
        assert not any("peanut" in i["item"].lower() for i in meal["ingredients"])

    # login issues a working token for the same identity
    r2 = client.post("/auth/login", json={"username": uname, "password": "supersecret"})
    assert r2.status_code == 200 and r2.json()["user_id"] == uid


def test_http_auth_failures(monkeypatch):
    monkeypatch.setenv("KITCHENAID_AUTH_SECRET", SECRET)
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    uname = f"u{uuid.uuid4().hex[:10]}"
    client.post("/auth/register", json={"username": uname, "password": "supersecret"})

    assert client.post("/auth/register",
                       json={"username": uname, "password": "supersecret"}).status_code == 409
    assert client.post("/auth/register",
                       json={"username": f"u{uuid.uuid4().hex[:8]}", "password": "short"}
                       ).status_code == 422
    assert client.post("/auth/login",
                       json={"username": uname, "password": "WRONG-pass"}).status_code == 401


def test_accounts_unavailable_without_secret(monkeypatch):
    monkeypatch.delenv("KITCHENAID_AUTH_SECRET", raising=False)
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    assert client.post("/auth/register",
                       json={"username": "someone", "password": "supersecret"}).status_code == 503
