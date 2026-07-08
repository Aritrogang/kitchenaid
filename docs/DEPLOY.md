# Deploy

The API ships as a container. The image runs migrations (when `DATABASE_URL` is set) and
serves `uvicorn kitchenaid.api:app` on port 8000 as a non-root user, with a `/health`
container healthcheck.

## Local stack (API + Postgres)

```bash
docker compose up --build
# API on http://localhost:8000  (GET /health, GET /agents, POST /chat)
```

Compose starts Postgres, waits for it to be healthy, and the API container applies migrations
on start. `ANTHROPIC_API_KEY` is passed through from your shell or `.env` if present — the
safety gate and corpus path run fine without it; only the Creative Chef's live generation
needs a key.

## Just the image

```bash
docker build -t kitchenaid-api .
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql://user:pass@host:5432/kitchenaid \
  kitchenaid-api
```

Without `DATABASE_URL` the image still starts and falls back to JSON file storage (migrate is
skipped) — fine for a smoke test, not for multi-user.

## Configuration

| Env | Purpose |
|---|---|
| `DATABASE_URL` | Postgres DSN. Unset → JSON files (single-node dev only). |
| `ANTHROPIC_API_KEY` | Enables live Creative Chef generation. Optional. |
| `KITCHENAID_MAX_USD_PER_DAY` | Spend guardrail cap (see `.env.example`). |

## Secrets

Never bake secrets into the image (`.env` is `.dockerignore`d and `.gitignore`d). Inject
`DATABASE_URL` and `ANTHROPIC_API_KEY` at runtime via your platform's secret manager
(compose env, ECS/K8s secrets, etc.).

## Not yet (tracked)

- Reverse proxy / TLS termination and the static web client's hosting.
- Connection pooling and horizontal scaling (`PostgresStore` connects per call today).
- CI publishing the image to a registry. Today CI only *builds* it to prove the Dockerfile.
