"""Ingredient resolution tests — the layer between a free-text chef and the canonical gate.

The headline property: resolution must respect allergen/diet DIRECTION. "vegan butter" is
dairy-free; it must never resolve to dairy "butter". A bug here re-introduces the exact
substring false-positive the attribute table was built to kill.

Runs with pytest, or standalone:  python3 tests/test_resolution.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import data  # noqa: E402
from kitchenaid.models import Ingredient, Profile, Recipe  # noqa: E402
from kitchenaid import resolution  # noqa: E402
from kitchenaid.resolution import classify, detect_modifier, resolve, violates_modifier  # noqa: E402
from kitchenaid.tools import gate  # noqa: E402


def _profile(**kw) -> Profile:
    base = dict(user_id="t", name="Test", allergies=[], diet="none")
    base.update(kw)
    return Profile.from_dict(base)


def _one(item) -> Recipe:
    return Recipe(id="r", name="R", cuisine="", time_min=10, servings=1, skill="beginner",
                  equipment=[], diet_tags=[], spice_level=0, ingredients=[Ingredient(item, 50)])


# --- the headline: direction is respected --------------------------------------------

def test_vegan_butter_never_resolves_to_dairy_butter():
    r = resolve("vegan butter")
    assert r.canonical == "vegan butter"
    assert r.canonical != "butter"
    # a vegan AND a milk-allergic user must BOTH be fine with vegan butter
    assert gate(_one("vegan butter"), _profile(diet="vegan")).approved is True
    assert gate(_one("vegan butter"), _profile(allergies=["milk"])).approved is True


def test_real_butter_still_blocks_vegan_and_milk_allergy():
    assert gate(_one("butter"), _profile(diet="vegan")).approved is False
    assert gate(_one("butter"), _profile(allergies=["milk"])).approved is False


def test_greek_yogurt_is_still_dairy():
    assert resolve("Greek yogurt").canonical == "greek yogurt"
    assert gate(_one("Greek yogurt"), _profile(diet="vegan")).approved is False
    assert gate(_one("Greek yogurt"), _profile(allergies=["milk"])).approved is False


def test_almond_milk_is_tree_nut_not_dairy():
    assert resolve("almond milk").canonical == "almond milk"
    # safe for a dairy allergy...
    assert gate(_one("almond milk"), _profile(allergies=["milk"])).approved is True
    # ...but trips a tree-nut allergy
    assert gate(_one("almond milk"), _profile(allergies=["tree_nut"])).approved is False


# --- synonyms + qualifiers -----------------------------------------------------------

def test_qualifier_stripping():
    assert resolve("low-sodium tamari").canonical == "tamari"
    assert resolve("organic fresh spinach").canonical == "spinach"
    assert resolve("boneless skinless chicken breast").canonical == "chicken breast"


def test_tamari_is_soy_but_wheat_free_unlike_soy_sauce():
    # soy sauce carries wheat; tamari does not — resolution must keep them distinct
    assert gate(_one("low-sodium tamari"), _profile(allergies=["soy"])).approved is False
    assert gate(_one("low-sodium tamari"), _profile(allergies=["wheat"])).approved is True
    assert gate(_one("soy sauce"), _profile(allergies=["wheat"])).approved is False


def test_prawns_resolve_to_shellfish():
    assert resolve("prawns").canonical == "shrimp"
    assert gate(_one("prawns"), _profile(allergies=["shellfish"])).approved is False


def test_unknown_text_is_unresolved():
    r = resolve("artisanal dragon glaze")
    assert r.canonical is None
    assert r.method == "unresolved"


def test_no_substring_fallback():
    """'buttermilk pancake mix' must NOT resolve to 'butter' or 'milk' via containment."""
    r = resolve("buttermilk pancake mix")
    assert r.canonical not in ("butter", "milk")
    assert r.canonical is None  # genuinely unknown -> fail closed, not a wrong guess


# --- coverage-expansion guardrails (the line that must not blur) ---------------------

def test_coverage_expansion_did_not_reintroduce_inversion():
    """The live-fire descendant of the peanut-butter test. After adding qualifier stripping
    and dozens of synonyms, a free-from string must STILL never resolve to a base that flips
    its allergen profile."""
    dairy_entries = {"butter", "cheddar cheese", "yogurt", "greek yogurt"}
    for s in ["vegan butter", "dairy-free butter", "vegan cheddar", "vegan cheese",
              "dairy-free cheese", "dairy-free milk", "egg-free mayo", "egg-free mayonnaise",
              "plant-based sausage", "vegan margarine"]:
        c = classify(s)
        assert c.outcome != "misresolved", f"{s!r} mis-resolved to {c.canonical!r}"
        assert c.canonical not in dairy_entries, f"{s!r} resolved to dairy {c.canonical!r}"
        if c.canonical:  # whatever the modifier excludes must not be present in the target
            mod, _ = detect_modifier(s)
            assert not violates_modifier(mod, c.canonical), f"{s!r} -> {c.canonical!r} violates {mod!r}"


def test_vegan_butter_resolves_to_dairy_free_after_expansion():
    assert resolve("vegan butter").canonical == "vegan butter"
    assert resolve("dairy-free butter").canonical == "vegan butter"
    assert gate(_one("vegan butter"), _profile(diet="vegan", allergies=["milk"])).approved is True


def test_descriptive_qualifiers_are_allergen_neutral():
    """Structural guard: no allergen-inverting modifier word may ever leak into the
    descriptive-strip set, or the two paths' opposite safety semantics collapse."""
    inverting_words = set()
    for phrase in resolution._INVERTING_MODIFIERS:
        inverting_words.update(phrase.split())
    leaked = inverting_words & resolution._QUALIFIERS
    assert not leaked, f"allergen-inverting words leaked into descriptive qualifiers: {leaked}"


def test_category_a_variety_strips_to_base():
    cases = {
        "yellow onion": "onion", "red onion": "onion", "firm tofu": "tofu",
        "brown lentils": "lentils", "crushed tomatoes": "tomato", "broccoli florets": "broccoli",
        "jasmine rice": "white rice", "elbow macaroni": "noodles", "garlic powder": "garlic",
    }
    for raw, expected in cases.items():
        assert resolve(raw).canonical == expected, f"{raw!r} -> {resolve(raw).canonical!r}, want {expected!r}"


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} resolution tests passed.")


if __name__ == "__main__":
    _run_standalone()
