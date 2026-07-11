"""Vercel serverless entrypoint — exposes the FastAPI ASGI app.

Vercel's @vercel/python runtime serves the module-level `app`. Configure the project's env:
  - DATABASE_URL           Postgres DSN (Vercel Postgres / Neon or external)
  - KITCHENAID_AUTH_SECRET a long random string — enables username/password login
  - ANTHROPIC_API_KEY      optional; enables the Creative Chef (corpus path works without it)

Run migrations once against the database before first use:
  DATABASE_URL=... python -m kitchenaid.store migrate

Serverless note: each invocation is stateless, so the in-memory "last meal" used to attach
feedback lives only within a warm instance. Profiles and taste persist in Postgres, so the
core (safe meal, shopping, weekly plan) is unaffected; deep session continuity is future work.
"""

import os
import sys

# The spend ledger must live on a writable path in the serverless filesystem (only written on
# paid calls). Set BEFORE importing kitchenaid, since the limiter reads config at import.
os.environ.setdefault("KITCHENAID_SPEND_LEDGER", "/tmp/kitchenaid_spend.jsonl")

# The package sits one level up from this function file.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.api import app  # noqa: E402  (exposed for the ASGI runtime)
