# Persistence

User state — a user's structured **profile** (allergies, diet, budget…) and their learned
**taste memory** — is written through a small store seam (`kitchenaid/store.py`) with two
interchangeable backends, keyed by `user_id`:

| Backend | When | Where state lives |
|---|---|---|
| `FileStore` | default (dev, CLI) | JSON: `state/<user_id>.profile.json`, `…​.taste.json` |
| `PostgresStore` | `DATABASE_URL` is set | a `profile` row and a `taste` row per user (JSONB) |

Everything above the store — `ProfileKeeper`, the HTTP API — is backend-agnostic. The gate
reads the profile from the request at decision time; this table is durable storage, not the
gate's authority, and taste only nudges ranking.

The API uses it directly: `POST /chat` persists the profile it's given (and lets later turns
omit it), and `GET`/`PUT /profile/{user_id}` read and write it.

## Selecting a backend

- **Files (default):** nothing to do. `ProfileKeeper()` writes to `state/`.
- **Postgres:** set `DATABASE_URL` and install the driver:
  ```bash
  pip install -e ".[db]"
  export DATABASE_URL=postgresql://user:password@localhost:5432/kitchenaid
  python -m kitchenaid.store migrate      # apply migrations/*.sql (idempotent)
  ```
  Now `ProfileKeeper()` — and therefore the API — reads and writes Postgres.

An **explicit** directory (`ProfileKeeper("/some/dir")`) always means files, even when
`DATABASE_URL` is set. That keeps tests and one-off tooling hermetic.

## Migrations

Forward-only SQL in `migrations/NNNN_*.sql`, applied in order and tracked in a
`schema_migrations` table. `python -m kitchenaid.store migrate` is safe to run on every
deploy — already-applied files are skipped.

## The JSON shape is the contract

Both backends serialize the same `to_dict()` payload (`Profile` and `TasteMemory`), so a user
can be lifted from files into Postgres by copying the JSON into the `data` column. Further
stores (spend ledger, sessions) follow the same seam.

## Not yet (tracked for production)

- Connection pooling (`psycopg_pool`) — `PostgresStore` connects per call today.
- Server-side **spend-ledger** + **session** tables (same seam).
- Encryption at rest for the health-adjacent profile fields (see `docs/PRODUCTION_READINESS.md` §4).
