# Phase 0 — Scope & Data

Phase 0 locks two things so every later phase has a stable contract to build on:

1. **The profile schema** — the structured user model.
2. **The deterministic sources** — a nutrition database, an allergen map, a dietary-rule
   engine, and a pricing source. These are the ground truth the Dietitian gate checks
   against. They use lookups and rules, **not model judgment**.

---

## 1. Profile schema

Defined as dataclasses in [`kitchenaid/models.py`](../kitchenaid/models.py); an example
profile lives in [`kitchenaid/data/profile.example.json`](../kitchenaid/data/profile.example.json).

| Field | Type | Role | Notes |
|------|------|------|------|
| `user_id` | str | identity | |
| `name` | str | display | |
| `allergies` | `list[str]` | **HARD RULE** | keys into the allergen map (`peanut`, `shellfish`, …). Never violable. |
| `diet` | str | **HARD RULE** | `none` \| `vegetarian` \| `vegan` \| `pescatarian` \| `halal` \| `kosher` |
| `calories_target` | int? | soft goal | per-serving target; over → flag, not reject |
| `protein_target_g` | int? | soft goal | per-serving floor |
| `budget_per_meal_usd` | float? | soft goal | over → flag |
| `equipment` | `list[str]` | soft constraint | missing gear → flag |
| `skill` | str | soft constraint | `beginner` \| `intermediate` \| `advanced` |
| `weeknight_minutes` | int | time norm | default time budget on a weeknight |
| `dislikes` | `list[str]` | preference | down-ranks, doesn't reject |
| `liked_dishes` | `list[str]` | taste memory (seed) | Phase 4 replaces with embeddings |
| `disliked_dishes` | `list[str]` | taste memory (seed) | Phase 4 replaces with embeddings |

### Hard rules vs soft goals — the central distinction

- **Hard rules** (`allergies`, `diet`) → a candidate that violates one is **rejected**.
  No score, no override, ever. This is the safety boundary that justifies splitting out
  the Dietitian in Phase 2.
- **Soft goals** (budget, macros, time, equipment, skill) → violations become **flags**.
  The agent can still surface the meal, transparently noting the tradeoff
  ("$1.20 over budget", "needs an oven you didn't list").

The "moment" (this dinner's constraints) is modeled separately as `Moment`
(time available, what's on hand, what's expiring, servings) so the persistent profile
never gets polluted with one-night state.

---

## 2. Deterministic sources

All four live in [`kitchenaid/data/`](../kitchenaid/data) as JSON and are loaded by
[`kitchenaid/data.py`](../kitchenaid/data.py). They were chosen to be **swappable**:
each is a thin local seed today, replaceable with a real API without touching the gate.

### a) Nutrition database — `nutrition.json`
Per-100g macros (`kcal`, `protein_g`, `carb_g`, `fat_g`) keyed by canonical ingredient.
Modeled on the field shape of **USDA FoodData Central** (FDC) so the seed table can be
swapped for the live FDC API (`api.nal.usda.gov/fdc`) behind the same `lookup_nutrition()`
function. FDC is free, authoritative, and government-maintained — the right Phase 3+ source.

### b) Ingredient-attribute table — `ingredients.json`  ← the safety authority
Each canonical ingredient declares **structured facts**: the allergens it carries and its
diet-relevant properties, e.g.
`peanut butter → {allergens: [peanut], diet_props: []}`,
`butter → {allergens: [milk], diet_props: [dairy, animal]}`.

This replaces naive substring matching, which has a dangerous failure mode: scanning the
string `"peanut butter"` for the dairy trigger `"butter"` produces a **false positive**
(and `"butternut squash"`, `"buttermilk"`, `"coconut milk"` all collide the same way). For
a safety gate, structured facts beat string-guessing. `allergens.json` is kept only as the
allergen *vocabulary* (key → display label); the ingredient→allergen mapping is the
authority. Coconut is mapped to `tree_nut` (FDA classification).

A fail-safe matters here: an ingredient **not** in the table cannot be verified, so for a
user with allergies the gate **refuses** it rather than risk a false negative.

### c) Dietary-rule engine — `diet_rules.json`
Each restricted diet maps to a set of **forbidden `diet_props`**
(`vegan → [meat, poultry, pork, fish, shellfish, dairy, egg, honey, gelatin, animal]`),
checked against each ingredient's attributes. The gate checks **ingredient properties**,
not the recipe's self-declared `diet_tags` — the verifier does not trust the proposer's
labels. Recipe `diet_tags` exist only to help the chef *pre-rank*; they are never the
authority.

### d) Pricing source — `prices.json`  ← weakest source, flagged
USD per 100g per ingredient. This is the least authoritative source: there is no good free
grocery-pricing API, so today it's a hand-seeded table of rough US averages. Real pricing
(store-specific, regional, live) is a Phase 3 problem — likely a retailer API or a scraped
price feed behind the same `lookup_price()` seam. Cost numbers are **estimates**, labeled
as such in output.

---

## 3. The gate contract (built in Phase 1, isolated in Phase 2)

[`kitchenaid/tools.py`](../kitchenaid/tools.py) exposes the deterministic checks as plain
functions and a single `gate(recipe, profile, moment) -> GateResult`:

```
GateResult:
  approved: bool                 # False if ANY hard violation
  hard_violations: list[str]     # allergen / diet — these block approval
  flags: list[str]               # budget / macro / time / equipment / skill — informational
  calories_per_serving, protein_per_serving_g
  cost_total_usd, cost_per_serving_usd
```

Invariant the tests pin down: **`approved == True` ⇒ `hard_violations == []`**.
In Phase 2 these functions move behind the Dietitian agent unchanged; the contract is
already the agent's interface.

### Two hardening properties the gate guarantees

- **Fail closed on every hard rule.** An ingredient that can't be resolved to a known
  entry blocks the plan whenever a hard rule is *active* — not just for allergic users but
  for vegan / halal / kosher / etc. too. (The first cut failed *open* on diet: an
  unverifiable ingredient slipped through a vegan plan. Fixed and pinned by
  `test_unknown_ingredient_blocks_restricted_diet`.) Fail-closed is scoped to active rules:
  a `diet=none`, no-allergy user has nothing to verify, so unknowns pass.
- **Allergens are category-based.** The profile stores allergen *categories* (`tree_nut`),
  and the ingredient table maps each ingredient to categories — so one `tree_nut` allergy
  rejects almond, cashew, walnut, coconut, … without enumerating them per-profile. Pinned
  by `test_tree_nut_allergy_rejects_every_tree_nut`.

### Ingredient resolution — the bridge to a generative chef

The deterministic chef only emits canonical ingredients, so fail-closed never fires in
Phase 1. A generative chef (Claude, Phase 3+) emits free text — "vegan butter",
"low-sodium tamari", "Greek yogurt", "prawns". [`kitchenaid/resolution.py`](../kitchenaid/resolution.py)
normalizes that to a canonical key **before** the gate runs, with a strict safety rule:
**no loose substring matching, ever** (it's `exact → synonym → strip cooking-qualifiers →
singularize → unresolved`). Direction is preserved: `vegan butter` resolves to a dairy-free
entry, never to dairy `butter`; `almond milk` is a tree nut, not dairy. Anything genuinely
unknown stays unresolved and the gate fails closed. This is what stops the substring bug
from reappearing on the LLM path. See [`examples/llm_chef_friction.py`](../examples/llm_chef_friction.py).

### Confidence: property-based fuzzing, not just example tests

[`tests/test_gate_properties.py`](../tests/test_gate_properties.py) fuzzes the gate over
hundreds of generated `profile × recipe` combinations (Hypothesis when installed; a
deterministic stdlib fuzzer otherwise) and asserts an exact oracle:
**`gate.approved` iff the recipe is genuinely safe**, recomputed independently from the
attribute table. This is the seed of the Phase 6 constraint-satisfaction eval — not
throwaway work.

---

## 4. Simplifications (intentional, documented)

These keep Phase 1 runnable today; each has a clear upgrade path.

- **Units**: every recipe ingredient is expressed in **grams** (discrete items converted,
  e.g. 1 egg ≈ 50 g). Real unit handling (cups, tbsp, "a can of") is deferred — it's a
  parsing/normalization layer, not a gate-logic change.
- **Pantry**: Phase 1 has no inventory. "What's on hand" comes from the moment/query.
  The pantry diff arrives in Phase 3 (the Shopper).
- **Intent parsing**: the moment is parsed with naive keyword/regex scanning. Real intent
  routing ("quick dinner" vs "plan the week" vs "use up the fridge") is the Concierge's
  job in Phase 5.
- **Corpus**: ~10 seed recipes in `recipes.json`. RAG over a real recipe corpus is a
  Phase 3+ swap behind the chef.
