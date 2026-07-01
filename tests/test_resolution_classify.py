"""Tests for the three-way resolution classifier, the mis-resolution detector, and the
live-fire fail-closed invariant.

The classifier is the instrument that turns the resolution gap into a dataset, so it has to
be sound BEFORE we trust its readings on a few hundred live samples.

Standalone:  python3 tests/test_resolution_classify.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import data, eval_resolution as ev  # noqa: E402
from kitchenaid.models import Ingredient, Recipe  # noqa: E402
from kitchenaid.resolution import classify, violates_modifier  # noqa: E402


def _cls(raw):
    return classify(raw)


# --- three-way classification --------------------------------------------------------

def test_clean_resolution():
    c = _cls("spinach")
    assert c.outcome == "resolved" and c.severity == "ok" and c.modifier is None


def test_benign_unresolved_is_low_severity():
    c = _cls("artisanal dragon glaze")
    assert c.outcome == "unresolved" and c.modifier is None and c.severity == "low"


def test_modifier_gap_is_medium_severity():
    # "vegan ricotta" has no canonical free-from variant yet -> unresolved (fail closed),
    # flagged medium because it's a modifier-prefixed gap (high-value to add later).
    c = _cls("vegan ricotta")
    assert c.outcome == "unresolved" and c.modifier == "vegan" and c.severity == "medium"


def test_modifier_respected_resolution():
    c = _cls("vegan butter")
    assert c.outcome == "resolved" and c.modifier == "vegan" and c.severity == "ok"


def test_qualifier_then_clean():
    assert _cls("low-sodium tamari").outcome == "resolved"
    assert _cls("fresh garlic").outcome == "resolved"


# --- the mis-resolution detector (the live-fire alarm for the substring bug) ---------

def test_misresolution_detector_fires_on_wrong_direction():
    # if "vegan butter" ever resolved to dairy "butter", THIS must catch it
    assert violates_modifier("vegan", "butter") is True
    assert violates_modifier("dairy-free", "cheddar cheese") is True
    assert violates_modifier("egg-free", "egg") is True
    assert violates_modifier("nut-free", "cashews") is True


def test_misresolution_detector_silent_on_correct_resolution():
    assert violates_modifier("vegan", "vegan butter") is False
    assert violates_modifier("dairy-free", "olive oil") is False
    assert violates_modifier("vegan", "tofu") is False  # tofu is soy, not animal/dairy


def test_current_resolver_produces_zero_misresolutions():
    """Sweep every modifier x base in the table: the resolver must never mis-resolve."""
    bases = list(data.ingredient_attrs().keys())
    mods = ["vegan", "dairy-free", "egg-free", "nut-free", "gluten-free", "plant-based"]
    for m in mods:
        for b in bases:
            assert classify(f"{m} {b}").outcome != "misresolved", f"{m} {b} mis-resolved"


# --- the live invariant (pure, scoped to active hard rules) --------------------------

def test_invariant_fires_when_approved_with_unknown_under_active_rule():
    unresolved = [_cls("mystery glaze")]
    assert ev.invariant_violated(True, unresolved, active_hard_rule=True) is True


def test_invariant_silent_when_no_active_hard_rule():
    unresolved = [_cls("mystery glaze")]
    assert ev.invariant_violated(True, unresolved, active_hard_rule=False) is False


def test_invariant_silent_when_rejected():
    unresolved = [_cls("mystery glaze")]
    assert ev.invariant_violated(False, unresolved, active_hard_rule=True) is False


def test_audit_does_not_raise_on_normal_inputs():
    from kitchenaid.models import Profile
    vegan = Profile.from_dict({"user_id": "v", "name": "V", "allergies": ["milk"], "diet": "vegan"})
    clean = Recipe(id="c", name="Clean", cuisine="", time_min=10, servings=1, skill="beginner",
                   equipment=[], diet_tags=[], spice_level=0,
                   ingredients=[Ingredient("lentils", 100), Ingredient("carrot", 50)])
    audit = ev.audit_recipe(clean, vegan)   # fully resolved, vegan-safe -> approved, no raise
    assert audit.approved is True


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} classifier/invariant tests passed.")


if __name__ == "__main__":
    _run_standalone()
