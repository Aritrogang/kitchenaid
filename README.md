# kitchenaid

A daily kitchen assistant you talk to — *"what should I make tonight?"*, *"plan my week,"*
*"I've got chicken and three things about to expire, help."* — built around a **deterministic,
fail-closed allergen safety gate** that a real LLM can propose to but never override.

### ▶︎ Live: **https://kitchenaid-amber.vercel.app**

> The live demo runs the deterministic safety gate over the recipe corpus (open mode). Turning on
> username/password **login** and the **AI chef** is a matter of setting three env vars —
> see [`docs/DEPLOY.md`](docs/DEPLOY.md).

It adapts on three axes:

1. **Your profile** — allergies (hard rules), diet, macro/calorie targets, budget, equipment, skill.
2. **Your learned tastes** — what you've rated *loved / too spicy / took too long*, which re-ranks future picks.
3. **The moment** — you have 20 minutes tonight and spinach that dies tomorrow.

It returns meals, recipes, safe substitutions, and an auto-built grocery list with cost — and
gets smarter every time you give feedback.

## The six agents

A **Concierge** routes each request and calls only the agents a turn needs:

| Agent | Role |
|---|---|
| **Concierge** | Reads intent (dinner / shopping / feedback / weekly plan) and assembles the answer |
| **Creative Chef** | Proposes dishes — from the corpus, or invented by an LLM from your exact words |
| **Dietitian** 🔒 | The safety gate — deterministic allergen/diet verification. **Not toggleable by design.** |
| **Shopper** | Pantry diff, costed grocery list, substitution → re-verify loop |
| **Profile Keeper** | Persists your profile + learned taste |
| **Taster** | Turns feedback into taste weights that shape the next suggestion |

The core thesis: **the safety gate is deterministic and fail-closed, and it survives contact with
a real model.** The Chef proposes; the Dietitian disposes.

## The safety guarantee

An allergen must **never** pass the gate — a property we test, not hope for:

```bash
python3 -m pytest tests/ -q            # 215 tests
python3 -m kitchenaid.eval_harness     # 0 unsafe approvals on frozen real dishes
```

- **Fail-closed on unknown ingredients** (allergen *and* diet) — an unresolved item blocks the dish.
- **Category-based** allergens — one `tree_nut` rule rejects every nut; the US "big 9" are pinned
  by [`tests/test_allergen_coverage.py`](tests/test_allergen_coverage.py).
- **Property-based fuzzing** ([`tests/test_gate_properties.py`](tests/test_gate_properties.py)) — hundreds
  of generated `profile × recipe` combos asserting `approved` iff genuinely safe.
- The **eval harness** replays real generated dishes × diverse profiles and asserts **0 unsafe
  approvals** on every push (CI).
- Even the creative LLM path can't bypass it: invented dishes go through the same gate, and if all
  are blocked it re-proposes — proven in tests and live.

## Run it locally

Zero dependencies for the core loop — it runs on the Python standard library.

```bash
# CLI
python3 -m kitchenaid "quick dinner, I've got chicken and spinach, 20 minutes"
python3 -m kitchenaid --demo          # canned scenarios incl. the allergen safety demo

# HTTP API (pip install "fastapi[standard]")
uvicorn kitchenaid.api:app --reload
curl -s localhost:8000/chat -H 'content-type: application/json' -d '{
  "user_id":"me","query":"what do I need to buy for dinner with rice?",
  "profile":{"user_id":"me","allergies":["shellfish"],"diet":"none","budget_per_meal_usd":6}}'

# Web client (static, zero-build)
python3 -m http.server 3000 --directory web    # then open http://localhost:3000
```

Set `ANTHROPIC_API_KEY` to enable the **live Creative Chef** (Claude invents dishes from your
words). The gate stays 100% deterministic either way — the model never gets the final say. A
fail-closed **spend guardrail** (`budget.py`) refuses paid calls before any cap is crossed.

## Web + iOS

- **`web/`** — a zero-build static SPA (vanilla ES modules): chat, meal cards, grocery lists, the
  agent-toggle panel with the locked Dietitian, and a **username/password login** so each user's
  allergies and taste are private to their account.
- **`ios/`** — a native SwiftUI app (MVVM) over the same `/chat` contract.

Accounts use salted **PBKDF2**; a signed **bearer token** carries identity (never client input);
**`DELETE /profile`** is a real right-to-erasure. See [`auth.py`](kitchenaid/auth.py) and
[`docs/PERSISTENCE.md`](docs/PERSISTENCE.md).

## Deploy your own

Pick a target — the API is one container / one function:

```bash
vercel --prod           # vercel.json: static web + Python function, same-origin
docker compose up       # Dockerfile + Postgres
# or connect the repo to Render (render.yaml blueprint)
```

Set `DATABASE_URL` (Postgres — profiles/taste/sessions persist with migrations),
`KITCHENAID_AUTH_SECRET` (turns on login), and optionally `ANTHROPIC_API_KEY`. Then
`python -m kitchenaid.store migrate`. Full guide: [`docs/DEPLOY.md`](docs/DEPLOY.md).

Production hardening that's already in: **rate limiting** (`/chat` + `/auth/*`, per user/IP, 429),
per-user **spend caps**, configurable **CORS**, secrets never in the image. CI runs 215 tests +
the safety eval across **Python 3.9–3.12**, a Postgres service, and a Docker build on every push.

## Layout

```
kitchenaid/
  kitchenaid/
    models.py · data.py · resolution.py   # schema, data sources, free-text → canonical
    tools.py                              # THE GATE — deterministic allergen/diet/cost checks
    chef.py · agent.py                    # candidate generation (corpus + optional Claude)
    dietitian.py · shopper.py · pantry.py # gated verifier, grocery + substitution loop
    taste.py · taster.py · profile_keeper.py   # learned taste + feedback
    concierge.py                          # intent routing, cost governor, trace
    api.py · store.py · accounts.py · auth.py · ratelimit.py   # HTTP: Postgres/file store, login, limits
    budget.py · config.py · eval_harness.py · mcp_server.py · cli.py
  web/          # static SPA client (with login)
  ios/          # native SwiftUI app
  migrations/   # forward-only SQL (users, profile, taste, session)
  tests/        # 215 tests — safety first
  docs/         # design, deploy, security, allergen-data, legal, privacy
```

## Honest status

The **hard part exists**: a deterministic, tested, fail-closed safety gate that survived real LLM
output with **zero unsafe approvals**, plus the full product around it (six agents, web + iOS,
auth, persistence, rate limiting, one-command deploy). Released as **v1.0.0**.

**Not yet cleared for real allergic users** — these need a human, not more code, and are flagged
in the docs, not faked: professional sign-off of the allergen data
([`docs/ALLERGEN_DATA.md`](docs/ALLERGEN_DATA.md)), and legal + privacy review
([`docs/LEGAL.md`](docs/LEGAL.md), [`docs/PRIVACY.md`](docs/PRIVACY.md)). Full picture:
[`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md).
```
