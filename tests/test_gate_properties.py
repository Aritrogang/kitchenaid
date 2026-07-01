"""Property-based fuzzing of the safety gate — the seed of the Phase 6 constraint eval.

The claim we ship on, stated as a property over hundreds of generated profile x recipe
combinations:

    gate(recipe, profile).approved  ==  recipe is genuinely safe for that profile

where "genuinely safe" is recomputed independently from the ingredient-attribute table:
no carried allergen intersects the profile's allergies, no ingredient property is forbidden
by the diet, and — when a hard rule is active — no ingredient is unverifiable.

Uses Hypothesis when installed (the real interview line); otherwise a deterministic stdlib
fuzzer so the property still runs everywhere. Standalone:  python3 tests/test_gate_properties.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import data  # noqa: E402
from kitchenaid.models import Ingredient, Profile, Recipe  # noqa: E402
from kitchenaid.tools import gate  # noqa: E402

CANON = sorted(data.ingredient_attrs().keys())
ALLERGENS = sorted(data.allergen_labels().keys())
DIETS = ["none", "vegetarian", "vegan", "pescatarian", "halal", "kosher"]
_UNKNOWN = "zzz unverifiable mystery ingredient"


def _expected_approved(canonical_items, allergies, diet, has_unknown) -> bool:
    """Independent oracle: derive the truth straight from the attribute table + rules."""
    attrs = data.ingredient_attrs()
    carried_allergens: set[str] = set()
    diet_props: set[str] = set()
    for it in canonical_items:
        carried_allergens |= set(attrs[it]["allergens"])
        diet_props |= set(attrs[it]["diet_props"])

    allergen_conflict = bool(set(allergies) & carried_allergens)

    rule = data.diet_rules().get(diet)
    forbidden = set(rule["forbidden_props"]) if rule else set()
    diet_conflict = bool(diet_props & forbidden)

    active_hard_rule = bool(allergies) or bool(rule)
    # an unverifiable ingredient blocks only when a hard rule is active
    unverifiable_block = has_unknown and active_hard_rule

    return not (allergen_conflict or diet_conflict or unverifiable_block)


def _assert_sound(canonical_items, allergies, diet, has_unknown):
    items = list(canonical_items) + ([_UNKNOWN] if has_unknown else [])
    recipe = Recipe(id="fuzz", name="Fuzz", cuisine="", time_min=10, servings=1,
                    skill="beginner", equipment=[], diet_tags=[], spice_level=0,
                    ingredients=[Ingredient(i, 50) for i in items])
    profile = Profile.from_dict({"user_id": "f", "name": "F",
                                 "allergies": list(allergies), "diet": diet})
    verdict = gate(recipe, profile)
    expected = _expected_approved(canonical_items, allergies, diet, has_unknown)

    assert verdict.approved == expected, (
        f"gate.approved={verdict.approved} but expected {expected} for "
        f"items={items}, allergies={allergies}, diet={diet}; hard={verdict.hard_violations}"
    )
    # the non-negotiable safety half: an approval may NEVER carry an allergen
    if verdict.approved:
        attrs = data.ingredient_attrs()
        carried = set().union(*(set(attrs[it]["allergens"]) for it in canonical_items)) if canonical_items else set()
        assert not (set(allergies) & carried)


try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    @settings(max_examples=500, deadline=None)
    @given(
        canonical_items=st.lists(st.sampled_from(CANON), min_size=1, max_size=6),
        allergies=st.lists(st.sampled_from(ALLERGENS), max_size=3, unique=True),
        diet=st.sampled_from(DIETS),
        has_unknown=st.booleans(),
    )
    def test_gate_is_sound_hypothesis(canonical_items, allergies, diet, has_unknown):
        _assert_sound(canonical_items, allergies, diet, has_unknown)

except ImportError:  # pragma: no cover - exercised when hypothesis isn't installed
    pass


def test_gate_is_sound_fuzz():
    """Deterministic stdlib fuzzer — always runs, even without Hypothesis."""
    rng = random.Random(1337)
    for _ in range(3000):
        canonical_items = rng.sample(CANON, rng.randint(1, 6))
        allergies = rng.sample(ALLERGENS, rng.randint(0, 3))
        diet = rng.choice(DIETS)
        has_unknown = rng.random() < 0.3
        _assert_sound(canonical_items, allergies, diet, has_unknown)


if __name__ == "__main__":
    test_gate_is_sound_fuzz()
    print("  ok  test_gate_is_sound_fuzz (3000 random profile x recipe combos)")
    if "test_gate_is_sound_hypothesis" in globals():
        print("  (hypothesis installed — pytest will also run 500 generated examples)")
    else:
        print("  (hypothesis not installed — `pip install hypothesis` for generative mode)")
    print("\nproperty holds: gate.approved iff genuinely safe.")
