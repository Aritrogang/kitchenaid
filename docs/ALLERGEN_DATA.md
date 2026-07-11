# Allergen data — provenance & the pre-launch bar

> 🔴 **Launch blocker.** The gate is only as safe as the ingredient→allergen data behind it.
> That data is currently **hand-tagged by an engineer**. Do **not** put this in front of real
> users with allergies until the data has professional review and a sourced provenance trail
> (below). The engineering is done; the *data* is not signed off.

## How the gate uses the data

`kitchenaid/data/ingredients.json` is the authority: each ingredient declares which allergens
it carries (structured facts, not substring matching — so "peanut butter" is not dairy "butter",
"coconut milk" is not dairy, and coconut → tree_nut per FDA). `allergens.json` is the vocabulary.
The Dietitian reads these; the model never decides allergen facts.

## What is already guaranteed (tested)

- **Vocabulary = the US "big 9"** (milk, egg, fish, crustacean shellfish, tree nuts, peanuts,
  wheat, soybeans, sesame — FDA / FASTER Act 2021). Pinned by `tests/test_allergen_coverage.py`
  so a category can't be silently dropped, and every category is carried by ≥1 ingredient so the
  gate can detect it.
- **Fail-closed on unknowns.** An unresolved ingredient blocks the dish; it never passes silently.
- **0 unsafe approvals** across a frozen corpus of real generated dishes × diverse profiles, plus
  property fuzzing — enforced in CI by the eval harness.
- **Over-tag, never under-tag** for ambiguous composite products ("vegan cheese" → union of
  possible allergens).

## The bar before launch (not yet met)

1. **Sourced dataset.** Replace/verify every ingredient→allergen mapping against an authoritative
   source (e.g. USDA FoodData Central, manufacturer labels, a licensed allergen DB) with a
   citation per entry.
2. **Change-audit trail.** Every edit to the allergen mapping reviewed and logged (who/when/why).
3. **Professional sign-off.** A qualified dietitian / food-safety reviewer signs off the mapping
   and the fail-closed behavior.
4. **Coverage on real traffic.** Track the unresolved-ingredient rate in production; each miss is
   safe (blocked) but hurts usability, and clustering reveals gaps to close.

Until 1–3 are done, treat any "safe" result as *assistive*, and keep the in-product disclaimer
(`kitchenaid/api.py::DISCLAIMER`) prominent.
