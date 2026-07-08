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

## 2. Agent architecture (the roadmap)
- 🟡 **Phase 2 — split the Dietitian** into its own gated agent (input contract decided by the
  live data: resolved *name*, not product).
- 🟡 **Phase 3 — Shopper**: pantry model + diff, grocery list w/ quantities & cost, substitution
  → re-verify loop through the Dietitian.
- 🟡 **Phase 4 — Profile Keeper + Taster**: persisted profiles + taste embeddings + feedback
  learning. Needs an embeddings provider (Voyage / OpenAI / local).
- 🟢 **Phase 5 — Concierge + MCP + tracing**: intent routing, cost-governor fast path, MCP
  server over the tools, observability.

## 3. Infrastructure & platform
- 🔴 **Persistence.** Profiles, pantry, taste memory, feedback, spend ledger are JSON/in-memory.
  Needs a real datastore (Postgres or similar) with migrations.
- 🔴 **Multi-user + auth.** Everything is single-user today. Need accounts, authentication, and
  per-user data isolation (profiles hold health data — see §4).
- ✅ **HTTP API.** Done — [`api.py`](../kitchenaid/api.py): a thin FastAPI adapter over the
  Concierge (`POST /chat`, `GET /health`), per-user session, taste persisted via the Profile
  Keeper, trace returned. `uvicorn kitchenaid.api:app`. Remaining: a **web/mobile client**.
- 🟡 **UI client.** A frontend (web or mobile) that calls `/chat`. The API contract is stable.
- 🟡 **Deployment.** Containerize, host, CI/CD, and move secrets from `.env` to a real secret
  manager.

## 4. Safety, compliance, liability
- 🔴 **Allergen guarantee at scale.** Core is the fail-closed gate (done). Production adds: the
  complete reviewed allergen DB (§1), graceful UX for "unknown ingredient → refuse" (ask/clarify,
  don't silently drop), and an **audit log of every gate decision**.
- 🔴 **Legal: allergy/medical disclaimer + terms.** An app making allergen claims needs legal
  review, clear disclaimers ("always verify labels yourself"), and a defined liability stance.
- 🔴 **Privacy.** Profiles are health data (allergies, medical diets). Needs a privacy policy,
  encryption at rest, and GDPR/CCPA handling as applicable.
- 🟡 **Prompt-injection hardening.** The chef consumes user free-text; the deterministic gate
  keeps *safety* intact regardless, but guard generation cost/quality against injection.

## 5. Cost & abuse controls
- 🔴 **Per-user budgets.** The spend guardrail is global/per-process today. Production needs
  per-user quotas and per-user spend tracking tied to accounts (the guardrail primitive extends
  cleanly to this).
- 🟡 **Caching.** Prompt caching + result caching to cut per-user cost at scale.
- 🟢 **Model routing.** Route cheap turns to Haiku, escalate only when warranted (Concierge).

## 6. Observability & ops
- 🟡 **Tracing** of every agent handoff (Phase 5).
- 🟡 **Metrics + alerting.** Track approval rate, resolution-miss rate, spend, latency, errors;
  alert on budget breach, gate anomalies, or a spike in the unresolved rate. The
  `resolution_misses.jsonl` dataset is already the seed of this signal.

## 7. Eval & QA / CI
- 🟡 **Eval harness (Phase 6).** Grow `test_gate_properties.py` (property fuzzing) + a frozen set
  of real generated dishes into a regression corpus. Track **ingredient-DB coverage %** (what
  fraction of real model output resolves) as a first-class metric.
- 🟡 **CI.** Run tests + evals on every change; block merges on any gate/safety regression.

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
