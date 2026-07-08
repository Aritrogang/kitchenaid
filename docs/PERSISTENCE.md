# Persistence

User state (learned **taste memory**, per `user_id`) is written through a small store seam
(`kitchenaid/store.py`) with two interchangeable backends:

| Backend | When | Where state lives |
|---|---|---|
| `FileStore` | default (dev, CLI) | JSON files under `state/<user_id>.taste.json` |
| `PostgresStore` | `DATABASE_URL` is set | a `taste` row per user (JSONB) |

Everything above the store — `ProfileKeeper`, the HTTP API — is backend-agnostic. The safety
gate never reads this data; taste only nudges ranking.

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

Both backends serialize the same `TasteMemory.to_dict()` payload, so a user can be lifted
from files into Postgres by copying the JSON into the `data` column. New stores (profiles,
spend ledger, sessions) follow the same seam and land with the auth/multi-user step.

## Not yet (tracked for production)

- Connection pooling (`psycopg_pool`) — `PostgresStore` connects per call today.
- Server-side **profile** + **spend-ledger** tables (same seam; arrive with auth/multi-user).
- Encryption at rest for the health-adjacent fields (see `docs/PRODUCTION_READINESS.md` §4).
