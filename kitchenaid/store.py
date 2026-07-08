"""Pluggable persistence for the Profile Keeper.

The store is the seam between the agents and where user state actually lives. Two backends
implement the same tiny interface:

  - FileStore     — JSON under state/ (the zero-dependency default; great for dev + CLI)
  - PostgresStore — a real datastore for production and multi-user

Selection is by environment: if DATABASE_URL is set, the default keeper uses Postgres;
otherwise it uses files. Everything above this line — ProfileKeeper, the HTTP API — is
backend-agnostic, so swapping the store never touches agent logic. psycopg is imported
lazily, so the core still installs and runs with no database driver present.

Run migrations with:  DATABASE_URL=... python -m kitchenaid.store migrate
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Protocol

from .taste import TasteMemory

_DEFAULT_STORE = Path(__file__).resolve().parent.parent / "state"
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class TasteStore(Protocol):
    """What the Profile Keeper needs from any backend. Deliberately small."""

    def get_taste(self, user_id: str) -> TasteMemory: ...
    def put_taste(self, user_id: str, memory: TasteMemory) -> None: ...


class FileStore:
    """JSON files under a directory — one `<user_id>.taste.json` per user."""

    def __init__(self, store_dir: "str | Path | None" = None) -> None:
        self.dir = Path(store_dir) if store_dir else _DEFAULT_STORE

    def _path(self, user_id: str) -> Path:
        return self.dir / f"{user_id}.taste.json"

    def get_taste(self, user_id: str) -> TasteMemory:
        return TasteMemory.load(self._path(user_id))          # missing file -> empty memory

    def put_taste(self, user_id: str, memory: TasteMemory) -> None:
        memory.save(self._path(user_id))


class PostgresStore:
    """Postgres backend. One row per user in `taste`, `data` a JSONB TasteMemory.

    Connects per call for simplicity and correctness in this first cut; a connection pool
    (psycopg_pool) is the clean next step once request volume warrants it.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def get_taste(self, user_id: str) -> TasteMemory:
        import psycopg

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT data FROM taste WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        # psycopg decodes JSONB straight to a dict; absent user -> fresh memory.
        return TasteMemory.from_dict(row[0]) if row else TasteMemory()

    def put_taste(self, user_id: str, memory: TasteMemory) -> None:
        import psycopg
        from psycopg.types.json import Json

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO taste (user_id, data, updated_at) VALUES (%s, %s, now()) "
                "ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data, updated_at = now()",
                (user_id, Json(memory.to_dict())),
            )
            conn.commit()


def make_store(store_dir: "str | Path | None" = None) -> TasteStore:
    """The default backend: Postgres when DATABASE_URL is set, else files.

    An explicit `store_dir` is NOT overridden by DATABASE_URL — a caller that names a
    directory means files (this keeps tests hermetic regardless of the environment).
    """
    if store_dir is not None:
        return FileStore(store_dir)
    dsn = os.getenv("DATABASE_URL")
    return PostgresStore(dsn) if dsn else FileStore(_DEFAULT_STORE)


# --- migrations ----------------------------------------------------------------------------

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
            for statement in (s.strip() for s in path.read_text(encoding="utf-8").split(";")):
                if statement:
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
