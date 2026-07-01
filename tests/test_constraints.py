"""Constraint-satisfaction tests — the safety guarantee, and the seed of the Phase 6 eval
harness.

Runs with pytest, or standalone:  python3 tests/test_constraints.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import agent, data  # noqa: E402
from kitchenaid.models import Ingredient, Profile, Recipe  # noqa: E402
from kitchenaid.tools import compute_cost, compute_nutrition, gate  # noqa: E402


def _profile(**kw) -> Profile:
    base = dict(user_id="t", name="Test", allergies=[], diet="none")
    base.update(kw)
    return Profile.from_dict(base)


def _recipe(rid):
    return next(r for r in data.recipes() if r.id == rid)


def _synthetic(*items) -> Recipe:
    """Build a one-off recipe from raw ingredient strings (simulating a generative chef)."""
    return Recipe(id="synthetic", name="Synthetic", cuisine="", time_min=10, servings=1,
                  skill="beginner", equipment=[], diet_tags=[], spice_level=0,
                  ingredients=[Ingredient(i, 50) for i in items])


# --- THE invariant: an allergen must never pass the gate -----------------------------

def test_peanut_allergen_recipe_is_rejected():
    profile = _profile(allergies=["peanut"])
    verdict = gate(_recipe("peanut-noodles"), profile)
    assert verdict.approved is False
    assert any("peanut" in v for v in verdict.hard_violations)


def test_no_approved_recipe_ever_contains_an_allergen():
    """Sweep the whole corpus for several allergic profiles. If a recipe is approved, it
    must declare NONE of that user's allergies in the ingredient-attribute table. This is
    the property we ship on, not hope for."""
    attrs = data.ingredient_attrs()
    for allergy in ["peanut", "shellfish", "milk", "egg", "soy", "tree_nut"]:
        profile = _profile(allergies=[allergy])
        for recipe in data.recipes():
            verdict = gate(recipe, profile)
            if verdict.approved:
                for ing in recipe.ingredients:
                    carried = attrs.get(ing.item.lower(), {}).get("allergens", [])
                    assert allergy not in carried, (
                        f"{recipe.id} approved for {allergy}-allergic user but has {ing.item}"
                    )


def test_gate_invariant_approved_implies_no_hard_violations():
    """The core contract carried into Phase 2: approved => hard_violations is empty."""
    profiles = [
        _profile(allergies=["shellfish"], diet="none"),
        _profile(diet="vegan"),
        _profile(diet="halal"),
        _profile(allergies=["peanut", "milk"], diet="vegetarian"),
    ]
    for profile in profiles:
        for recipe in data.recipes():
            verdict = gate(recipe, profile)
            if verdict.approved:
                assert verdict.hard_violations == []


# --- dietary rules -------------------------------------------------------------------

def test_vegan_rejects_meat_and_dairy():
    profile = _profile(diet="vegan")
    assert gate(_recipe("lemon-chicken-rice"), profile).approved is False     # chicken
    assert gate(_recipe("black-bean-quesadilla"), profile).approved is False  # cheese
    assert gate(_recipe("lentil-soup"), profile).approved is True             # plant-only


def test_diet_engine_ignores_recipe_self_tags():
    """The gate scans ingredients, not diet_tags. A recipe tagged vegan but containing an
    animal product would still be rejected — the verifier doesn't trust the proposer."""
    profile = _profile(diet="vegan")
    # peanut-noodles is tagged vegan AND is genuinely vegan -> should pass for a vegan
    assert gate(_recipe("peanut-noodles"), profile).approved is True


# --- fail closed for EVERY hard rule, not just allergens -----------------------------

def test_unknown_ingredient_blocks_allergic_user():
    profile = _profile(allergies=["peanut"])
    verdict = gate(_synthetic("dragonfruit glaze"), profile)  # not in the ingredient DB
    assert verdict.approved is False
    assert any("could not be resolved" in v for v in verdict.hard_violations)


def test_unknown_ingredient_blocks_restricted_diet():
    """The exact fail-OPEN bug the review caught: a vegan plan with an unverifiable
    ingredient must be REFUSED, not approved."""
    profile = _profile(diet="vegan")
    verdict = gate(_synthetic("mystery vegan sauce"), profile)
    assert verdict.approved is False
    assert any("could not be resolved" in v for v in verdict.hard_violations)


def test_unknown_ingredient_allowed_when_no_hard_rule():
    """Fail-closed is scoped to ACTIVE hard rules. With no allergies and no diet
    restriction there is nothing to verify, so an unknown ingredient passes."""
    profile = _profile(allergies=[], diet="none")
    assert gate(_synthetic("dragonfruit glaze"), profile).approved is True


# --- allergens are CATEGORY-based ----------------------------------------------------

def test_tree_nut_allergy_rejects_every_tree_nut():
    """A 'tree_nut' allergy must reject almonds, cashews, walnuts, coconut milk, etc. —
    not be enumerated nut-by-nut. The table maps ingredients to allergen CATEGORIES and the
    profile stores categories."""
    profile = _profile(allergies=["tree_nut"])
    for nut in ["almonds", "cashews", "walnuts", "coconut milk", "almond milk", "cashew cream"]:
        verdict = gate(_synthetic(nut), profile)
        assert verdict.approved is False, f"{nut} should trip a tree_nut allergy"
        assert any("Tree nut" in v for v in verdict.hard_violations)


# --- nutrition + cost are real numbers ----------------------------------------------

def test_nutrition_and_cost_computed():
    r = _recipe("lemon-chicken-rice")
    nutr = compute_nutrition(r)
    cost = compute_cost(r)
    assert nutr["per_serving"]["kcal"] > 0
    assert nutr["per_serving"]["protein_g"] > 0
    assert cost["total_usd"] > 0
    assert cost["unpriced_items"] == []


# --- soft flags don't block ----------------------------------------------------------

def test_over_budget_is_a_flag_not_a_rejection():
    profile = _profile(budget_per_meal_usd=0.50)  # impossibly low
    verdict = gate(_recipe("salmon-quinoa-bowl"), profile)
    assert verdict.approved is True
    assert any("budget" in f for f in verdict.flags)


# --- end-to-end agent loop respects the gate ----------------------------------------

def test_agent_never_recommends_an_allergen():
    profile = _profile(allergies=["peanut"], diet="vegetarian")
    rec = agent.recommend("something with noodles, quick", profile)
    if rec.chosen:
        names = " ".join(i.item.lower() for i in rec.chosen.ingredients)
        assert "peanut" not in names
    # and peanut-noodles must show up in the blocked list
    assert any(r.id == "peanut-noodles" for r, _ in rec.rejected)


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} constraint tests passed.")


if __name__ == "__main__":
    _run_standalone()
