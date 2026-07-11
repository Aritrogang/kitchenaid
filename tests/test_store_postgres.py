"""Postgres-backend persistence tests.

These run only when a database is reachable — the whole module skips if psycopg isn't
installed or DATABASE_URL isn't set, so the default suite stays green with no DB. CI runs
them against a real Postgres service (see .github/workflows/ci.yml). Each test uses a unique
user_id so runs never collide on shared state.

Local:  DATABASE_URL=postgresql://... python -m kitchenaid.store migrate
        DATABASE_URL=postgresql://... python -m pytest tests/test_store_postgres.py
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("psycopg", reason="psycopg not installed")  # skip module if no driver

from kitchenaid.models import Profile  # noqa: E402
from kitchenaid.profile_keeper import ProfileKeeper  # noqa: E402
from kitchenaid.store import FileStore, PostgresStore, make_store, run_migrations  # noqa: E402
from kitchenaid.taste import TasteMemory  # noqa: E402

DSN = os.getenv("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL not set")


@pytest.fixture(scope="module", autouse=True)
def _migrated():
    """Apply migrations once; also proves the runner is idempotent by running it twice."""
    run_migrations(DSN)
    assert run_migrations(DSN) == []          # second run applies nothing
    return DSN


def _uid(tag):
    return f"{tag}-{uuid.uuid4()}"


def test_missing_user_returns_empty_memory():
    store = PostgresStore(DSN)
    mem = store.get_taste(_uid("missing"))
    assert mem.spice_tolerance == 0.0 and mem.cuisine == {}


def test_roundtrip_persists_all_fields():
    store = PostgresStore(DSN)
    uid = _uid("rt")
    store.put_taste(uid, TasteMemory(spice_tolerance=-1.0, time_pref=-0.5,
                                     cuisine={"Thai": 0.6}, loved=["Pad See Ew"]))
    got = store.get_taste(uid)
    assert got.spice_tolerance == -1.0
    assert got.time_pref == -0.5
    assert got.cuisine.get("Thai") == 0.6
    assert "Pad See Ew" in got.loved


def test_upsert_overwrites_not_duplicates():
    store = PostgresStore(DSN)
    uid = _uid("upsert")
    store.put_taste(uid, TasteMemory(spice_tolerance=-1.0))
    store.put_taste(uid, TasteMemory(spice_tolerance=-2.0))   # same user, new value
    assert store.get_taste(uid).spice_tolerance == -2.0


def test_profile_roundtrip_and_upsert():
    store = PostgresStore(DSN)
    uid = _uid("prof")
    assert store.get_profile(uid) is None                    # absent -> None
    store.put_profile(uid, Profile.from_dict(
        {"user_id": uid, "name": "P", "allergies": ["Sesame"], "diet": "Vegan",
         "budget_per_meal_usd": 9.0}))
    got = store.get_profile(uid)
    assert got.allergies == ["sesame"] and got.diet == "vegan" and got.budget_per_meal_usd == 9.0
    store.put_profile(uid, Profile.from_dict({"user_id": uid, "name": "P2"}))   # upsert, not dup
    refreshed = store.get_profile(uid)
    assert refreshed.name == "P2" and refreshed.allergies == [] and refreshed.diet == "none"


def test_delete_erases_profile_and_taste():
    store = PostgresStore(DSN)
    uid = _uid("del")
    store.put_profile(uid, Profile.from_dict({"user_id": uid, "allergies": ["peanut"]}))
    store.put_taste(uid, TasteMemory(spice_tolerance=-1.0))
    store.delete(uid)
    assert store.get_profile(uid) is None
    assert store.get_taste(uid).spice_tolerance == 0.0        # fresh again
    store.delete(uid)                                          # idempotent: deleting nothing is fine


def test_make_store_selects_postgres_from_env():
    # DATABASE_URL is set (module skips otherwise), and no explicit dir -> Postgres.
    assert isinstance(make_store(), PostgresStore)
    # An explicit directory always means files, even with DATABASE_URL set (test isolation).
    assert isinstance(make_store("/tmp/kitchenaid-explicit"), FileStore)


def test_profilekeeper_default_uses_postgres_and_persists():
    keeper = ProfileKeeper()                     # no dir -> env-driven backend
    assert isinstance(keeper._store, PostgresStore)
    uid = _uid("pk")
    mem = keeper.load_taste(uid)
    mem.spice_tolerance = -1.5
    keeper.save_taste(uid, mem)
    assert ProfileKeeper().load_taste(uid).spice_tolerance == -1.5   # survives a new keeper
