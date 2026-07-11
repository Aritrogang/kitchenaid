"""Pluggable persistence for the Profile Keeper.

The store is the seam between the agents and where user state actually lives. Two backends
implement the same tiny interface, keyed by `user_id`:

  - FileStore     — JSON under state/ (the zero-dependency default; great for dev + CLI)
  - PostgresStore — a real datastore for production and multi-user

It holds the two persistent pieces of a user: their learned **taste** and their structured
**profile** (allergies, diet, budget…). Selection is by environment: if DATABASE_URL is set,
the default keeper uses Postgres; otherwise it uses files. Everything above this line —
ProfileKeeper, the HTTP API — is backend-agnostic, so swapping the store never touches agent
logic. psycopg is imported lazily, so the core still installs and runs with no driver present.

Run migrations with:  DATABASE_URL=... python -m kitchenaid.store migrate
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Protocol

from .models import Profile
from .taste import TasteMemory

_DEFAULT_STORE = Path(__file__).resolve().parent.parent / "state"
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class Store(Protocol):
    """What the Profile Keeper needs from any backend. Deliberately small."""

    def get_taste(self, user_id: str) -> TasteMemory: ...
    def put_taste(self, user_id: str, memory: TasteMemory) -> None: ...
    def get_profile(self, user_id: str) -> Optional[Profile]: ...
    def put_profile(self, user_id: str, profile: Profile) -> None: ...


class FileStore:
    """JSON files under a directory: `<user_id>.taste.json` and `<user_id>.profile.json`."""

    def __init__(self, store_dir: "str | Path | None" = None) -> None:
        self.dir = Path(store_dir) if store_dir else _DEFAULT_STORE

    def _taste_path(self, user_id: str) -> Path:
        return self.dir / f"{user_id}.taste.json"

    def _profile_path(self, user_id: str) -> Path:
        return self.dir / f"{user_id}.profile.json"

    def get_taste(self, user_id: str) -> TasteMemory:
        return TasteMemory.load(self._taste_path(user_id))    # missing file -> empty memory

    def put_taste(self, user_id: str, memory: TasteMemory) -> None:
        memory.save(self._taste_path(user_id))

    def get_profile(self, user_id: str) -> Optional[Profile]:
        path = self._profile_path(user_id)
        if not path.exists():
            return None
        return Profile.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def put_profile(self, user_id: str, profile: Profile) -> None:
        path = self._profile_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")


class PostgresStore:
    """Postgres backend: a `taste` row and a `profile` row per user, each `data` a JSONB blob.

    Connects per call for simplicity and correctness in this first cut; a connection pool
    (psycopg_pool) is the clean next step once request volume warrants it.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def get_taste(self, user_id: str) -> TasteMemory:
        row = self._get_one("taste", user_id)
        return TasteMemory.from_dict(row) if row is not None else TasteMemory()

    def put_taste(self, user_id: str, memory: TasteMemory) -> None:
        self._upsert("taste", user_id, memory.to_dict())

    def get_profile(self, user_id: str) -> Optional[Profile]:
        row = self._get_one("profile", user_id)
        return Profile.from_dict(row) if row is not None else None

    def put_profile(self, user_id: str, profile: Profile) -> None:
        self._upsert("profile", user_id, profile.to_dict())

    # Both tables share the (user_id, data jsonb) shape, so one pair of helpers serves both.
    def _get_one(self, table: str, user_id: str) -> Optional[dict]:
        import psycopg

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT data FROM {table} WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        return row[0] if row else None            # psycopg decodes JSONB straight to a dict

    def _upsert(self, table: str, user_id: str, data: dict) -> None:
        import psycopg
        from psycopg.types.json import Json

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO {table} (user_id, data, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()",
                (user_id, Json(data)),
            )
            conn.commit()


def make_store(store_dir: "str | Path | None" = None) -> Store:
    """The default backend: Postgres when DATABASE_URL is set, else files.

    An explicit `store_dir` is NOT overridden by DATABASE_URL — a caller that names a
    directory means files (this keeps tests hermetic regardless of the environment).
    """
    if store_dir is not None:
        return FileStore(store_dir)
    dsn = os.getenv("DATABASE_URL")
    return PostgresStore(dsn) if dsn else FileStore(_DEFAULT_STORE)


# --- migrations ----------------------------------------------------------------------------

def _sql_statements(text: str) -> list[str]:
    """Split a migration file into individual statements. Strips `--` line comments first so
    a semicolon *inside a comment* never fakes a statement boundary (DDL only — no string
    literals containing `--` or `;`)."""
    without_comments = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    return [s.strip() for s in without_comments.split(";") if s.strip()]


def run_migrations(dsn: Optional[str] = None) -> list[str]:
    """Apply any unapplied `migrations/*.sql` in order, tracked in `schema_migrations`.
    Forward-only and idempotent — safe to run on every deploy. Returns the files applied."""
    import psycopg

    dsn = dsn or os.environ["DATABASE_URL"]
    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    applied: list[str] = []
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        cur.execute("SELECT name FROM schema_migrations")
        done = {r[0] for r in cur.fetchall()}
        for path in files:
            if path.name in done:
                continue
            for statement in _sql_statements(path.read_text(encoding="utf-8")):
                cur.execute(statement)
            cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            applied.append(path.name)
        conn.commit()
    return applied


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "migrate":
        done = run_migrations()
        print(f"migrations applied: {done or 'none (already up to date)'}")
    else:
        print("usage: python -m kitchenaid.store migrate   (uses $DATABASE_URL)")
        raise SystemExit(2)
