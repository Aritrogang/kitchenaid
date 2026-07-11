# Deploy

The API ships as a container. The image runs migrations (when `DATABASE_URL` is set) and
serves `uvicorn kitchenaid.api:app` on port 8000 as a non-root user, with a `/health`
container healthcheck.

## Vercel (static web + API as a serverless function)

`vercel.json` deploys both the static web client and the FastAPI backend (a Python serverless
function) from this repo. The web app calls the API same-origin — no CORS setup needed.

```bash
npm i -g vercel          # or use npx vercel
vercel login
vercel --prod            # from the repo root
```

Set these in the Vercel project (Settings → Environment Variables), then redeploy:

| Env | Value |
|---|---|
| `DATABASE_URL` | a Postgres DSN (Vercel Postgres / Neon, or external) |
| `KITCHENAID_AUTH_SECRET` | a long random string — turns on username/password login |
| `ANTHROPIC_API_KEY` | optional — enables the Creative Chef |

Run migrations once against that database (creates the users / profile / taste tables):

```bash
DATABASE_URL='postgres://…' python -m kitchenaid.store migrate
```

Open the deployment: with `KITCHENAID_AUTH_SECRET` set you get the **login screen** — register,
set your profile, and your data is private to your account.

**Serverless caveat:** Vercel functions are stateless, so the in-memory "last meal" that feedback
attaches to only lives within a warm instance. Profiles and taste persist in Postgres, so
meals / shopping / weekly plans are unaffected; persisting the last-meal session is tracked
follow-up. For an always-on container, use the Render blueprint below.

## One-click: Render (API + Postgres)

`render.yaml` is a Blueprint. In the Render dashboard: **New → Blueprint → connect this repo.**
It provisions Postgres, builds the image, runs migrations on start, health-checks `/health`, and
**generates `KITCHENAID_AUTH_SECRET` so auth is on out of the box** (every request needs a token).
Optionally set `ANTHROPIC_API_KEY` in the dashboard to enable live generation. Before going
public, set `KITCHENAID_CORS_ORIGINS` to your web origin(s) and put it behind TLS.

(Any Docker host works — the blueprint just wires it for you. Fly.io / Railway / ECS follow the
same shape: build the Dockerfile, attach Postgres, set the env below.)

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
| `KITCHENAID_AUTH_SECRET` | Set → auth required, identity from token. Unset → open (dev only). |
| `ANTHROPIC_API_KEY` | Enables live Creative Chef generation. Optional. |
| `KITCHENAID_CORS_ORIGINS` | `*` (dev) or a comma-separated web-origin allowlist (production). |
| `KITCHENAID_MAX_USD_PER_DAY` / `_PER_USER_PER_DAY` | Spend caps (see `.env.example`). |

## Accounts & the login flow

With `KITCHENAID_AUTH_SECRET` set, users register and then carry a Bearer token:

```bash
# 1. register -> {user_id, token}
curl -sX POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"a-strong-password"}'
# 2. save your profile (allergies gate every meal)
curl -sX PUT $API/profile/$USER_ID -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"allergies":["peanut"],"diet":"vegetarian"}'
# 3. chat — no user_id needed, identity is the token; DELETE /profile/$USER_ID to erase everything
curl -sX POST $API/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"query":"quick dinner"}'
```

A user can only read/write their own data; the safety gate holds regardless.

## Secrets

Never bake secrets into the image (`.env` is `.dockerignore`d and `.gitignore`d). Inject
`DATABASE_URL` and `ANTHROPIC_API_KEY` at runtime via your platform's secret manager
(compose env, ECS/K8s secrets, etc.).

## Not yet (tracked)

- TLS termination (reverse proxy) and hosting the static web client.
- Edge rate-limiting (the per-user spend cap limits cost, not request volume).
- Connection pooling and horizontal scaling (`PostgresStore` connects per call today).
- CI publishing the image to a registry. Today CI only *builds* it to prove the Dockerfile.
