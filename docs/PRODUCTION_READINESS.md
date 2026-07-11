# Production readiness — what's left to ship

"Production" here means: real users, on a non-CLI surface, using it daily, with a
**safety-critical** allergen guarantee and real money flowing to the LLM. What exists today
is a correct, well-tested single-user engine with a deterministic safety gate and a proven
resolution loop. Below is everything between that and shipping, by area, with priority.

Legend: 🔴 blocks launch · 🟡 needed soon after · 🟢 scale/polish.

---

## 1. Data — accuracy & completeness (the safety foundation)
The gate is only as good as the ingredient data behind it. This is the highest-leverage area.

- 🔴 **Authoritative allergen data.** The ingredient-attribute table (`ingredients.json`) is
  the safety authority and is currently **hand-tagged**. Production needs a sourced, reviewed
  allergen dataset with a change-audit trail — not one engineer's judgment. Every entry that
  carries an allergen (fish sauce→fish, tahini→sesame, coconut→tree_nut, farro→wheat, …) must
  be verifiable.
- 🔴 **Ingredient DB completeness.** Fail-closed means every unknown ingredient blocks a dish.
  On live model output, coverage went 42%→60% after one pass; the long tail (comma-compounds,
  regional items, brands) still fails closed. Needs either a much larger curated DB or an
  LLM/embedding-assisted resolver — **with the deterministic gate still the authority** (never
  let a model resolve allergens).
- 🔴 **Compound / structured ingredient parsing.** Real output emits `"salt and pepper"`,
  `"mozzarella cheese, shredded"`, `"pancetta, diced"` — one string, multiple ingredients +
  prep clauses. Today these are mapped or fail closed; production needs real splitting
  (one string → many `Ingredient`s).
- 🟡 **Real nutrition source.** Macros are plausible hand seeds. Swap in **USDA FoodData
  Central** behind the existing `data.lookup_nutrition()` seam for accurate, sourced macros.
- 🟡 **Real pricing source.** Prices are hand-seeded US averages (the weakest source). Needs a
  retailer API / price feed, ideally regional, behind `data.lookup_price()`.
- 🟢 **Product-identity** ("vegan cheese" = cashew/soy/coconut). Live data shows this is rare,
  so it stays **union-flagged** (over-tag, never under-tag) for now; revisit only if data says
  it's common.

## 2. Agent architecture (the roadmap) — ✅ SHIPPED
The six-agent team is built and tested; these were the Phase 2–5 splits, now done.
- ✅ **Phase 2 — Dietitian** is its own gated agent (`dietitian.py`); the input contract is the
  resolved *name* (decided by the live data). Chef proposes, Dietitian disposes.
- ✅ **Phase 3 — Shopper** (`shopper.py` + `pantry.py`): pantry diff, costed grocery list,
  substitution → re-verify loop back through the Dietitian.
- ✅ **Phase 4 — Profile Keeper + Taster** (`profile_keeper.py`, `taster.py`, `taste.py`):
  persisted profiles + a deterministic taste model + feedback learning. Embeddings remain the
  documented swap behind the same `score()` seam.
- ✅ **Phase 5 — Concierge + MCP + tracing** (`concierge.py`, `mcp_server.py`): intent routing,
  cost-governor fast path, MCP server over the tools, per-handoff trace.

## 3. Infrastructure & platform
- 🟡 **Persistence.** ✅ Server-side **profiles** and learned **taste** now persist through a
  pluggable store — Postgres or JSON, selected by `DATABASE_URL` — with forward-only migrations
  (`docs/PERSISTENCE.md`); the API persists the profile and lets later turns omit it
  (`GET`/`PUT /profile/{user_id}`). CI verifies the Postgres path against a real service.
  Remaining on the same seam: pantry, feedback, and the spend ledger; connection pooling.
- 🟡 **Multi-user + auth.** ✅ Bearer-token auth, opt-in via `KITCHENAID_AUTH_SECRET`: when set,
  every request's identity comes from a verified signed token (stdlib HS256, fixed-alg,
  constant-time) — never client input — and a user can only read/write their own profile & taste.
  Remaining: wire token *issuance* to a real credential source (OAuth / SSO / password) — the
  deployment's auth-provider choice.
- ✅ **HTTP API.** Done — [`api.py`](../kitchenaid/api.py): a thin FastAPI adapter over the
  Concierge (`POST /chat`, `GET /health`), per-user session, taste persisted via the Profile
  Keeper, trace returned. `uvicorn kitchenaid.api:app`. Remaining: a **web/mobile client**.
- ✅ **UI client.** Two frontends over the stable `/chat` contract: a zero-build web SPA (`web/`)
  and a native SwiftUI iOS app (`ios/`), both with the agent-toggle panel and the locked
  Dietitian. iOS still needs an Xcode build/device pass.
- 🟡 **Deployment.** ✅ Containerized — `Dockerfile` + `docker-compose.yml` (API + Postgres),
  non-root, healthcheck, migrate-on-start; CI builds and smoke-tests the image (`docs/DEPLOY.md`).
  Remaining: host it, TLS/reverse proxy, publish to a registry, secrets in a real manager.

## 4. Safety, compliance, liability
- 🔴 **Allergen guarantee at scale.** Fail-closed gate (done); vocabulary pinned to the big 9 and
  0 unsafe approvals enforced in CI; in-product disclaimer live. **Still blocking:** professional
  sign-off + sourced provenance for the ingredient→allergen data (`docs/ALLERGEN_DATA.md`), an
  audit log of every gate decision, and graceful "unknown ingredient" UX.
- 🔴 **Legal: disclaimer + terms.** ✅ A disclaimer is returned with every answer and a template
  is drafted (`docs/LEGAL.md`). **Still blocking:** a lawyer must review the terms/disclaimer and
  liability stance, plus a recorded user-acceptance flow.
- 🔴 **Privacy.** ✅ Right-to-erasure endpoint (`DELETE /profile`) and a template are in place
  (`docs/PRIVACY.md`). **Still blocking:** published policy, lawful basis/consent for health data,
  encryption-at-rest confirmed, retention + full DSAR (export) flow.
- 🟡 **Prompt-injection hardening.** The chef consumes user free-text; the deterministic gate
  keeps *safety* intact regardless, but guard generation cost/quality against injection.

## 5. Cost & abuse controls
- 🟡 **Per-user budgets.** ✅ The spend guardrail now records spend per `user_id` and enforces
  opt-in per-user daily caps (`KITCHENAID_MAX_{USD,CALLS}_PER_USER_PER_DAY`) alongside the global
  cap — one user can't drain the account. Remaining: tie the caps to real accounts (auth) and
  move the ledger to Postgres for multi-node (same store seam).
- 🟡 **Caching.** Prompt caching + result caching to cut per-user cost at scale.
- 🟢 **Model routing.** Route cheap turns to Haiku, escalate only when warranted (Concierge).

## 6. Observability & ops
- 🟡 **Tracing** of every agent handoff (Phase 5).
- 🟡 **Metrics + alerting.** Track approval rate, resolution-miss rate, spend, latency, errors;
  alert on budget breach, gate anomalies, or a spike in the unresolved rate. The
  `resolution_misses.jsonl` dataset is already the seed of this signal.

## 7. Eval & QA / CI
- ✅ **Eval harness (Phase 6).** `eval_harness.py` replays 15 frozen real dishes × 7 profiles,
  asserting 0 mis-resolutions + 0 unsafe approvals + a coverage floor (currently 97.6%);
  property fuzzing lives in `test_gate_properties.py`. Coverage % is tracked as a first-class
  metric. Now wired into CI.
- ✅ **CI.** GitHub Actions (`.github/workflows/ci.yml`) runs the full suite + the safety eval
  keyless on every push/PR across Python 3.9–3.12, plus a Postgres-service job and a Docker
  image build/smoke-test; the eval exits non-zero on any regression, so it gates the build.
  Remaining: branch protection requiring the checks before merge.

## 8. UX
- 🟡 **Fail-closed UX.** Rejecting on unknown ingredients is safe but reads as "broken." Product
  needs to clarify/substitute/ask rather than silently block.
- 🟢 Feedback capture (Taster), grocery-list export, weekly planning surface.

---

## The honest one-liner
The **hard part — a deterministic, tested, fail-closed safety gate that survived real LLM
output with zero unsafe approvals — exists.** What's left is mostly *productization*: real
data sources (allergen DB, FDC, pricing), the platform (persistence, auth, API, UI), and the
compliance/ops scaffolding any health-adjacent product needs. The launch-blockers (🔴) cluster
in **data accuracy, persistence/auth, and legal/privacy** — not in the core engineering, which
is the point of having earned each piece.

## Launch gate — what's done vs. what a human must still sign off

**Engineering, done + CI-verified:** deterministic fail-closed gate · pluggable Postgres
persistence (profiles + taste) · opt-in Bearer-token auth with per-user isolation · per-user
spend caps · containerized API + compose · right-to-erasure · in-product disclaimer · big-9
allergen invariant · 199 tests + safety eval green on 3.9–3.12.

**Cannot be closed by code alone — required before serving real allergic users:**

- [ ] 🔴 **Allergen data** professionally reviewed + sourced with provenance (`ALLERGEN_DATA.md`).
- [ ] 🔴 **Legal** review of terms/disclaimer + recorded acceptance flow (`LEGAL.md`).
- [ ] 🔴 **Privacy** policy, health-data consent, encryption-at-rest, retention (`PRIVACY.md`).
- [ ] 🟡 **Auth issuance** wired to a real credential provider (OAuth/SSO); token *verification* is done.
- [ ] 🟡 **Deploy hardening**: restrict CORS, TLS, secrets manager, edge rate-limiting (`SECURITY.md`).

The honest status: **the product is engineering-complete and safe-by-construction, but it is
not launch-ready for real allergic users until the allergen data and the legal/privacy items
above are signed off by qualified people.**
