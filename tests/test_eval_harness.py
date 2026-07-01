"""Phase 6 tests — the eval harness as a regression gate over FROZEN real dishes.

Safety is the hard constraint (must be perfect); coverage has a floor; and a few specific
real dishes have their safety behavior pinned so a data regression can't slip through.

Standalone:  python3 tests/test_eval_harness.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import eval_harness as ev  # noqa: E402
from kitchenaid.eval_harness import COVERAGE_FLOOR, run_eval  # noqa: E402
from kitchenaid.models import Profile  # noqa: E402
from kitchenaid.tools import gate  # noqa: E402


def _dish(name):
    d = next(x for x in ev._load() if x["name"] == name)
    return ev._to_recipe(d)


def _p(allergies, diet="none"):
    return Profile.from_dict({"user_id": "t", "name": "t", "allergies": allergies, "diet": diet})


# --- the hard constraint-satisfaction guarantees -------------------------------------

def test_zero_misresolutions_on_real_fixtures():
    assert run_eval().misresolved == 0


def test_zero_unsafe_approvals_on_real_fixtures():
    r = run_eval()
    assert r.unsafe_approvals == 0, r.unsafe_examples


def test_coverage_above_floor():
    assert run_eval().coverage >= COVERAGE_FLOOR


def test_eval_overall_passes():
    assert run_eval().passes is True


# --- pinned behavior of specific real dishes (freeze the data) -----------------------

def test_specific_real_dishes_block_the_right_allergens():
    assert gate(_dish("Shrimp Scampi Pasta"), _p(["shellfish"])).approved is False
    assert gate(_dish("Pad Thai with Peanut Sauce"), _p(["peanut"])).approved is False
    assert gate(_dish("Buddha Bowl with Quinoa and Tahini Dressing"), _p(["sesame"])).approved is False
    assert gate(_dish("Greek Salad with Feta"), _p([], "vegan")).approved is False
    assert gate(_dish("Veggie Omelette with Toast"), _p(["egg"])).approved is False
    assert gate(_dish("Beef and Broccoli Stir Fry"), _p([], "vegetarian")).approved is False


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} eval-harness tests passed.")


if __name__ == "__main__":
    _run_standalone()
