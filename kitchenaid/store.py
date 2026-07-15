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

from .accounts import DuplicateUser
from .models import Profile, Recipe
from .taste import TasteMemory

_DEFAULT_STORE = Path(__file__).resolve().parent.parent / "state"
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class Store(Protocol):
    """What the Profile Keeper needs from any backend. Deliberately small."""

    def get_taste(self, user_id: str) -> TasteMemory: ...
    def put_taste(self, user_id: str, memory: TasteMemory) -> None: ...
    def get_profile(self, user_id: str) -> Optional[Profile]: ...
    def put_profile(self, user_id: str, profile: Profile) -> None: ...
    # Session: the last meal, so feedback attaches to it even across stateless (serverless) turns.
    def get_last_recipe(self, user_id: str) -> Optional[Recipe]: ...
    def put_last_recipe(self, user_id: str, recipe: Optional[Recipe]) -> None: ...
    def delete(self, user_id: str) -> None: ...   # erase all of a user's stored data
    # Accounts (username/password login).
    def create_user(self, user_id: str, username: str, password_hash: str) -> None: ...
    def get_user(self, username: str) -> Optional[dict]: ...   # {user_id, username, password_hash}


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

    def _session_path(self, user_id: str) -> Path:
        return self.dir / f"{user_id}.session.json"

    def get_last_recipe(self, user_id: str) -> Optional[Recipe]:
        path = self._session_path(user_id)
        if not path.exists():
            return None
        return Recipe.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def put_last_recipe(self, user_id: str, recipe: Optional[Recipe]) -> None:
        path = self._session_path(user_id)
        if recipe is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(recipe.to_dict(), indent=2), encoding="utf-8")

    def delete(self, user_id: str) -> None:
        for path in (self._taste_path(user_id), self._profile_path(user_id),
                     self._session_path(user_id)):
            path.unlink(missing_ok=True)
        users = self._load_users()                       # erase the account too, if any
        for name in [n for n, rec in users.items() if rec.get("user_id") == user_id]:
            users.pop(name)
        self._write_users(users)

    # --- accounts (a single users.json map, username -> record) ---
    def _users_path(self) -> Path:
        return self.dir / "users.json"

    def _load_users(self) -> dict:
        path = self._users_path()
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _write_users(self, users: dict) -> None:
        self._users_path().parent.mkdir(parents=True, exist_ok=True)
        self._users_path().write_text(json.dumps(users, indent=2), encoding="utf-8")

    def create_user(self, user_id: str, username: str, password_hash: str) -> None:
        users = self._load_users()
        if username in users:
            raise DuplicateUser(username)
        users[username] = {"user_id": user_id, "username": username, "password_hash": password_hash}
        self._write_users(users)

    def get_user(self, username: str) -> Optional[dict]:
        return self._load_users().get(username)


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

    def get_last_recipe(self, user_id: str) -> Optional[Recipe]:
        row = self._get_one("session", user_id)
        return Recipe.from_dict(row) if row is not None else None

    def put_last_recipe(self, user_id: str, recipe: Optional[Recipe]) -> None:
        if recipe is None:
            import psycopg
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM session WHERE user_id = %s", (user_id,))
                conn.commit()
            return
        self._upsert("session", user_id, recipe.to_dict())

    def delete(self, user_id: str) -> None:
        import psycopg

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM taste WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM profile WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM session WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            conn.commit()

    def create_user(self, user_id: str, username: str, password_hash: str) -> None:
        import psycopg
        from psycopg import errors

        try:
            with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO users (user_id, username, password_hash) "
                            "VALUES (%s, %s, %s)", (user_id, username, password_hash))
                conn.commit()
        except errors.UniqueViolation:
            raise DuplicateUser(username)

    def get_user(self, username: str) -> Optional[dict]:
        import psycopg

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT user_id, username, password_hash FROM users WHERE username = %s",
                        (username,))
            row = cur.fetchone()
        return {"user_id": row[0], "username": row[1], "password_hash": row[2]} if row else None

    # Both taste/profile tables share the (user_id, data jsonb) shape, so one pair serves both.
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
    if dsn:
        return PostgresStore(dsn)
    # No database: files. KITCHENAID_STATE_DIR lets a read-only-FS host (e.g. serverless)
    # point the store at a writable path like /tmp; otherwise the repo's state/ dir.
    return FileStore(os.getenv("KITCHENAID_STATE_DIR") or _DEFAULT_STORE)


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
