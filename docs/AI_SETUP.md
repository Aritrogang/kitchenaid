# AI / API setup — what to add, and when

The core loop and the **safety gate run with zero API access** — that's deliberate, not a
limitation. Only *generation* talks to an LLM. This doc is the map of where AI shows up so
you provision exactly what each phase needs and nothing more.

## Now: run the live Creative Chef (unblocks the real resolution-miss dataset)

1. **Get a key** — [console.anthropic.com](https://console.anthropic.com) → API Keys. Add a
   few dollars of credit; the run below costs well under a cent.
2. **Install the one optional dep** (core stays zero-dep):
   ```bash
   pip install anthropic
   ```
3. **Set the key** (use `.env`, which is gitignored — never commit a key):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
4. **Run it:**
   ```bash
   python3 examples/generative_chef_run.py 20      # invent 20 recipes, classify, log misses
   ```
   It auto-switches from SIMULATED to LIVE. If it stays SIMULATED it now tells you why
   (missing key / missing SDK). To see a live call that *errored* (auth, parse, model id),
   run with `KITCHENAID_DEBUG=1`.

**Cost:** generation defaults to **Haiku** (`claude-haiku-4-5-20251001`) on purpose — ~20
recipes is a fraction of a cent; a few hundred for the dataset is still cents.

**Spend guardrail (on by default).** A deterministic budget gate refuses any paid call
*before* it fires if it would cross a cap — per-run calls (25), per-day calls (200), or
per-day USD (**$1.00**). Fails closed (unknown model → priced as the most expensive;
unreadable ledger → refuses). Actual spend is logged to `eval/spend_ledger.jsonl`
(gitignored). Raise the caps via `KITCHENAID_MAX_USD_PER_DAY` etc. only if you mean to. See
[`kitchenaid/budget.py`](../kitchenaid/budget.py).

## The AI surface by role (so you know what's coming)

| Component | Phase | Needs | Model / provider |
|---|---|---|---|
| **Creative Chef** | now | text generation (Messages API) | Haiku (cheap, high-volume); Sonnet/Opus for richer invention |
| **Dietitian / the gate** | done | **nothing — deterministic** | ❌ no LLM, ever. The safety layer must not depend on a model. |
| **Concierge** (router + cost governor) | 5 | intent classification + routing | Haiku to classify; routes up to Sonnet/Opus only when the turn warrants it |
| **Profile Keeper / Taster** (taste memory) | 4 | **embeddings** | separate provider — see below |
| **MCP server** | 5 | none itself (wraps the tools) | n/a — it's how a host calls the deterministic tools |

All model choices live in one place: [`kitchenaid/config.py`](../kitchenaid/config.py)
(`MODELS` by role + `ai_status()` preflight), overridable by env var.

## The one extra thing to plan for: embeddings (Phase 4)

Taste memory = embedding the dishes you rate and matching "things like the meals you score
highly." **Anthropic does not serve a first-party embeddings endpoint**, so this needs a
*second* provider — one of:
- **Voyage AI** — Anthropic's recommended embeddings partner (separate key, `VOYAGE_API_KEY`).
- **OpenAI** `text-embedding-3-small/large` — if you already have an OpenAI key.
- **Local** — `sentence-transformers` (e.g. `bge-small`) — no API, runs offline, zero marginal cost.

For a portfolio build, **Anthropic for generation + one embeddings source** is the clean
story. Crucially: embeddings only drive *taste similarity* (a soft signal). They never touch
a hard rule — allergens and diet stay deterministic in the gate. (Verify the current
embeddings recommendation in Anthropic's docs when you get there; it shifts.)

## Secrets hygiene
`.env` is gitignored; `.env.example` documents every var. Never commit a key. When you add
embeddings you'll add exactly one more var (e.g. `VOYAGE_API_KEY`).
