# Roadmap

The thesis: **start as a single agent and earn each split.** Every decomposition is
justified by an engineering force (a safety boundary, a dependency loop, a cost governor),
not by org-chart neatness.

## The agent team (target architecture)

1. **Concierge** (orchestrator) — conversational front door. Holds the session, interprets
   intent, decides which specialists to call and in what order, assembles the answer.
   Planner–executor. Also the **cost governor**: a plain "what's for dinner" must not spin
   up the whole team.
2. **Profile Keeper** (memory) — the evolving user model: structured facts (allergies =
   hard rules, diet, macros, budget, equipment, skill, time) plus **taste memory**
   (embeddings of liked/disliked dishes). Reads/writes the persistent store.
3. **Creative Chef** (generation) — proposes candidate dishes / a week's plan. Higher
   temperature, RAG over a recipe corpus, free to invent. It **proposes — it never gets
   the final say.**
4. **Dietitian** (constraint + nutrition — **the gate**) — the verifier. Checks every
   candidate against hard rules with **deterministic tools, not judgment**: allergen
   checker, dietary-rule engine, nutrition lookup (USDA FDC), cost calculator. Rejects or
   flags. *An allergen must never pass this gate.*
5. **Shopper** (pantry + sourcing) — reconciles the approved plan against pantry inventory,
   computes exactly what to buy with quantities and cost, proposes substitutions for
   missing / over-budget items — which it sends **back through the Dietitian to re-verify**
   (no swapping peanut oil for a nut-allergic user). The re-verification loop is the clean
   example of agents depending on each other.
6. **Taster** (feedback/learning) — after a meal, captures *loved it / too spicy / took too
   long / made too much* and updates the Profile Keeper's taste memory and weights. Closes
   the loop that makes the system adaptive rather than static.

## Phases

### Phase 0 — Scope & data ✅
Lock the profile schema; pick deterministic sources (nutrition DB, allergen map,
dietary-rule engine, pricing). → [`PHASE_0_DESIGN.md`](PHASE_0_DESIGN.md)

### Phase 1 — Single-agent MVP ✅
One agent: profile → suggest a meal → check constraints **inline**. No team yet, so we have
a working loop fast. The gate lives in its own module (`tools.py`) called inline — already
shaped like the future agent boundary.

### Phase 1.5 — Harden the gate (done, before any decomposition)
Decomposition is nearly free by design, so there is no cost to deferring it and real cost
to splitting before the gate is trustworthy. Landed first:
- **Ingredient resolution layer** ([`resolution.py`](../kitchenaid/resolution.py)) — normalizes
  free-text chef output to canonical keys with no loose substring matching; the spec for it
  is the friction a real LLM chef hits against its own gate.
- **Fail closed on every hard rule** (not just allergens) + an explicit unknown-ingredient test.
- **Property-based fuzzing** of the gate (the seed of the Phase 6 eval).

### Phase 2 — Split out the Dietitian ✅
First decomposition, justified by the **safety boundary** — and done only after the gate
survived real LLM output (0 mis-resolutions across 725+ live strings). The deterministic
checks now live behind the [`Dietitian`](../kitchenaid/dietitian.py) agent: the Creative Chef
PROPOSES, the Dietitian DISPOSES (`review` / `review_batch`), and the agent loop no longer
knows the gate logic. `GateResult` was already the contract, so the split was nearly free.
Every verdict is logged (`Dietitian.decisions`) — the seed of Phase 5 tracing + the audit
trail. Safety invariant re-pinned at the agent level in `tests/test_dietitian.py`.

### Phase 3 — Add the Shopper ✅
[`shopper.py`](../kitchenaid/shopper.py): pantry diffing ([`pantry.py`](../kitchenaid/pantry.py)),
grocery list with quantities + cost, and the **substitution re-verification loop** — every
over-budget swap is sent back through the Dietitian, so a swap can never introduce an allergen
(demo: `salmon→tofu` is vetoed for a soy-allergic user and falls back to `cod`). The first
inter-agent dependency: the Shopper proposes, the Dietitian disposes. Budget is soft, allergens
hard — the Shopper refuses to break a hard rule to hit budget. Pinned in `tests/test_shopper.py`.

### Phase 4 — Add the Profile Keeper + Taster ✅
[`taste.py`](../kitchenaid/taste.py) (feature-based `TasteMemory` with a `score()` the Chef's
ranker adds in), [`taster.py`](../kitchenaid/taster.py) (feedback → weight updates: loved /
disliked / too spicy / too long / too much), [`profile_keeper.py`](../kitchenaid/profile_keeper.py)
(persists taste per user). Built **deterministic-first**; real semantic embeddings are a clean
swap behind `TasteMemory.score()`. Demo: `examples/feedback_demo.py` — loving a dish promotes
its cuisine, a spice complaint demotes spicy dishes.

Building this surfaced a real bug: with a key present, `chef.propose` was calling the Claude
corpus-reranker **every turn** — bypassing taste and spending money on every recommend/test.
Fixed: the taste-aware deterministic ranker is now the default (free, reproducible); LLM
rerank is opt-in via `KITCHENAID_LLM_RERANK=1` and re-applies taste on top. (Cost-governor
principle, early.)

### Phase 5 — MCP + Concierge + observability ✅
[`concierge.py`](../kitchenaid/concierge.py): the orchestrator/front door — deterministic
intent routing (quick_dinner / use_fridge / shopping / feedback / plan_week), session memory
(feedback attaches to the last meal), and the **cost governor** (a plain dinner spins up 2
agents, no Shopper, no LLM; the team only grows when the turn needs it). Every handoff is
recorded in a **trace** (`format_trace`) — observability. [`mcp_server.py`](../kitchenaid/mcp_server.py)
exposes the deterministic tools (`verify_recipe`, `resolve_ingredient`, `nutrition_of`,
`cost_of`) over MCP as thin adapters over the same core — no safety logic re-implemented.
Demos: `examples/concierge_demo.py`. Tests: `test_concierge.py`, `test_mcp_server.py`.

### Phase 6 — Eval harness ✅ · ship ⏳ (needs infra/UI decisions)
Eval harness built ([`eval_harness.py`](../kitchenaid/eval_harness.py)), **constraint-satisfaction
first**: replays a frozen corpus of REAL generated dishes ([`eval/fixtures/real_dishes.json`](../eval/fixtures/real_dishes.json))
across 7 profiles and asserts **0 mis-resolutions and 0 unsafe approvals** (the latter
re-derived independently from the attribute table), plus a **coverage floor** so a resolver
regression fails the build. Current: 0/0 unsafe, 97.6% coverage, PASS. The generated half is
the Hypothesis fuzzer in `tests/test_gate_properties.py`. Run: `python3 -m kitchenaid.eval_harness`.

**Ship** is the remaining user-gated work: the UI surface (web/mobile), a thin FastAPI over
the agent loop, deploy, and the launch-blockers in [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md)
(authoritative allergen DB, persistence, auth, legal/privacy). Then instrument daily-active
use — the user count is the resume line.
