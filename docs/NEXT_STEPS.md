# Next steps — the runway to finish

Where it stands: Phases 0–1.5 done, the generative-chef resolution loop proven on simulated
data, gate hardened (39 tests green). Everything below is **sequenced** — each milestone is
earned by the one before it. Owner tags: 🧑 you · 🤖 me · 🤝 together.

---

## Setup — tooling 🧑 (one-time)
Run in an **interactive `claude` terminal** (these `/plugin` commands don't work in every environment):
```
/plugin marketplace add wshobson/agents
/plugin install llm-application-dev      # RAG, vector search, agent architectures
/plugin install python-development       # Py 3.12+, FastAPI, async
/plugin install tdd-workflows            # red-green-refactor + review
/plugin install comprehensive-review     # architecture/security/best-practice review
```
Defer the phase-specific plugins (agent-orchestration, data-validation-suite, backend-development, api-scaffolding) until their phase below.

## 0. Unblock the live run 🧑 — *gates everything below*
- [ ] Get an Anthropic API key (console.anthropic.com) + add a few $ credit
- [ ] `pip install anthropic` && `export ANTHROPIC_API_KEY=sk-ant-...`
- [ ] `python3 examples/generative_chef_run.py 12` — eyeball classifications, confirm **MISRESOLVED = 0**
- [ ] Scale to ~60–100 dishes (run a few times; it accumulates), then send me `eval/resolution_misses.jsonl`

## 1. Settle the resolution fork 🤝 — *read from the jsonl*
- [ ] Classify the misses: **lookup-table** (one string → one allergen profile) vs **product-identity** (one string → many, e.g. "vegan cheese" = cashew/soy/coconut)
- [ ] Record the decision — it sets the Dietitian's input contract (a resolved *name* vs a resolved *product*)
- [ ] 🤖 patch synonyms (if lookup-table) or design product resolution (if product-identity)

## 2. Phase 2 — split out the Dietitian 🤖 — *depends on the fork*
- [ ] Standalone Dietitian agent; the chef **proposes → hands off →** the Dietitian verifies (not an inline call)
- [ ] `GateResult` contract unchanged; all existing tests stay green
- [ ] This is the first real agent/trust boundary

## 3. Phase 3 — the Shopper 🤖
- [ ] Pantry model + pantry-diff (what you have vs what the plan needs)
- [ ] Auto grocery list: quantities + estimated cost
- [ ] Substitution proposals → **re-verify loop** back through the Dietitian (no unsafe swaps)

## 4. Phase 4 — Profile Keeper + Taster 🤝
- [ ] 🧑 pick an embeddings provider (Voyage / OpenAI / local `sentence-transformers`)
- [ ] 🤖 taste memory: embed rated dishes, match "things like what you scored highly"
- [ ] 🤖 Taster: capture feedback (loved it / too spicy / too long / made too much), update weights
- [ ] Replaces the seed liked/disliked lists — embeddings drive *taste only*, never hard rules

## 5. Phase 5 — MCP + Concierge + observability 🤖
- [ ] Wrap the deterministic tools in an MCP server (thin adapters over `tools.py` / `resolution.py`)
- [ ] Concierge: intent routing + **cost-governor fast path** (a plain "what's for dinner" doesn't spin up the whole team)
- [ ] Trace every agent handoff (observability)

## 6. Phase 6 — eval harness + ship 🤝 — *the resume line*
- [ ] 🤖 grow the property/constraint tests into a real eval harness (constraint-satisfaction first)
- [ ] 🧑 decide the UI surface (web / mobile) → 🤖 thin FastAPI + minimal UI over the existing agent loop
- [ ] 🧑 ship to roommates / dorm floor; instrument **daily-active use**
- [ ] Track the user count — that's the line on the resume

---

## Cross-cutting 🧑 (do whenever)
- [ ] `git init` + commit the current green state (it's a portfolio piece — version history matters)
- [ ] Keep `eval/resolution_misses.jsonl` accumulating across real runs

## If the key stays blocked
The live run is the principled gate, but don't stall forever. If you can't get a key soon,
proceed on the **lookup-table assumption** (the likely outcome) into Phase 2 — the current
`vegan cheese = {tree_nut, soy}` union-flagging keeps you safe meanwhile — and revisit the
fork if real data later proves it product-identity. Note that as an explicit assumption so
future-you knows it wasn't validated.
