# kitchenaid

A kitchen agent you talk to daily — *"what should I make tonight?"*, *"plan my week,"*
*"I've got chicken and three things about to expire, help."*

It adapts on three axes:

1. **Your fixed profile** — allergies (hard rules), diet, macro/calorie targets, budget, equipment, skill, time norms.
2. **Your learned tastes** — what you've rated well or poorly (Phase 4).
3. **The moment** — you have 20 minutes tonight and spinach that dies tomorrow.

It outputs meals, recipes, substitutions, and an auto-built grocery list with cost,
and gets smarter every time you give feedback.

## Status

| Phase | Scope | State |
|------|-------|-------|
| **0** | Profile schema + deterministic data sources | ✅ done — see [`docs/PHASE_0_DESIGN.md`](docs/PHASE_0_DESIGN.md) |
| **1** | Single-agent MVP: profile → suggest meal → check constraints inline | ✅ done — this repo |
| **1.5** | Gate hardening: ingredient resolution, fail-closed everywhere, property fuzzing | ✅ done |
| **2** | Split out the **Dietitian** as a gated agent (propose→verify handoff) | ✅ done — [`dietitian.py`](kitchenaid/dietitian.py) |
| **3** | **Shopper**: pantry diff, grocery list, cost, substitution re-verify loop | ✅ done — [`shopper.py`](kitchenaid/shopper.py) |
| **4** | **Profile Keeper** + **Taster**: taste memory + feedback learning | ✅ done — [`taster.py`](kitchenaid/taster.py) |
| **5** | MCP server, **Concierge** routing + fast-path, observability | ✅ done — [`concierge.py`](kitchenaid/concierge.py) |
| **6** | Eval harness (constraint-satisfaction first) → ship | ✅ eval done · ⏳ ship (needs infra/UI) |

Full plan: [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Quick start

No dependencies required for the core loop — it runs on the Python standard library
with a deterministic fallback chef.

```bash
cd kitchenaid

# Ask for a quick dinner with what you have on hand
python3 -m kitchenaid "quick dinner, I've got chicken and spinach, 20 minutes"

# Use up the fridge
python3 -m kitchenaid --profile kitchenaid/data/profile.example.json "use up the fridge"

# See the gate in action across a few canned scenarios (incl. the allergen safety demo)
python3 -m kitchenaid --demo
```

### Turn on the real Creative Chef (optional)

If `ANTHROPIC_API_KEY` is set, the chef uses Claude to rank and frame suggestions.
The **safety gate stays 100% deterministic either way** — the LLM proposes, it never
gets the final say.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install anthropic        # only needed for the Claude path
python3 -m kitchenaid "something cozy, I have lentils and carrots"
```

## The safety guarantee

An allergen must **never** pass the gate. That's a property we test, not hope for:

```bash
python3 -m pytest tests/ -q        # or: python3 tests/test_constraints.py
```

- `tests/test_constraints.py` — hard rules, incl. **fail-closed on unknown ingredients**
  (allergen *and* diet) and **category-based** allergens (one `tree_nut` rule rejects every nut).
- `tests/test_resolution.py` — free-text → canonical, with the safety direction pinned
  (`vegan butter` never resolves to dairy `butter`; no substring fallback).
- `tests/test_gate_properties.py` — **property-based fuzzing**: hundreds of generated
  `profile × recipe` combos, asserting `gate.approved` iff genuinely safe (Hypothesis when
  installed, stdlib fuzzer otherwise). The seed of the Phase 6 eval.

Watch the resolution layer handle a simulated generative chef (no API key needed):

```bash
python3 examples/llm_chef_friction.py
```

## Layout

```
kitchenaid/
  kitchenaid/
    models.py      # dataclasses: Profile, Moment, Recipe, GateResult
    data.py        # loads nutrition / allergen / price / recipe sources
    tools.py       # THE GATE — deterministic allergen/diet/nutrition/cost checks
    chef.py        # candidate generation (deterministic fallback + optional Claude)
    agent.py       # single-agent loop: profile + moment → propose → gate → answer
    cli.py         # `python -m kitchenaid ...`
    data/          # seed JSON: nutrition, ingredients (allergen+diet facts), prices, recipes
  docs/            # Phase 0 design + roadmap
  tests/           # constraint-satisfaction tests (safety first)
```
