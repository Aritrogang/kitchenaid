"""Phase 3 tests — the Shopper: pantry diff, costed grocery list, and the substitution
re-verify loop.

The headline is the inter-agent safety property: a swap that would introduce an allergen or
diet violation is REJECTED because it must pass the Dietitian again. The Shopper proposes;
the Dietitian still disposes.

Standalone:  python3 tests/test_shopper.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import data  # noqa: E402
from kitchenaid.dietitian import Dietitian  # noqa: E402
from kitchenaid.models import Profile  # noqa: E402
from kitchenaid.pantry import Pantry  # noqa: E402
from kitchenaid.shopper import Shopper  # noqa: E402


def _recipe(rid):
    return next(r for r in data.recipes() if r.id == rid)


def _profile(**kw) -> Profile:
    base = dict(user_id="t", name="t", allergies=[], diet="none")
    base.update(kw)
    return Profile.from_dict(base)


# --- pantry diff + grocery list ------------------------------------------------------

def test_pantry_diff_removes_what_you_have():
    r = _recipe("lemon-chicken-rice")               # includes chicken breast 300g
    pantry = Pantry.from_dict({"chicken": 300})      # 'chicken' resolves to chicken breast
    plan = Shopper().plan(r, pantry, _profile())
    bought = {gi.item for gi in plan.items}
    assert "chicken breast" not in bought            # fully on hand -> not on the list
    assert "white rice" in bought                    # not on hand -> on the list


def test_grocery_list_has_quantities_and_cost():
    r = _recipe("lentil-soup")
    plan = Shopper().plan(r, Pantry(), _profile())
    assert plan.total_cost_usd > 0
    assert all(gi.grams > 0 and gi.est_cost_usd >= 0 for gi in plan.items)
    assert abs(plan.total_cost_usd / max(r.servings, 1) - plan.cost_per_serving_usd) < 0.02


# --- over-budget substitution --------------------------------------------------------

def test_over_budget_triggers_a_cheaper_verified_substitution():
    r = _recipe("salmon-quinoa-bowl")                # salmon is expensive
    plan = Shopper().plan(r, Pantry(), _profile(), budget_per_serving=3.0)
    assert plan.substitutions                         # at least one swap applied
    assert all(s.verified for s in plan.substitutions)
    final = {i.item for i in plan.recipe.ingredients}
    assert "salmon" not in final                      # swapped for something cheaper


# --- THE inter-agent safety loop -----------------------------------------------------

def test_substitution_never_introduces_an_allergen():
    """A soy-allergic user: the cheapest salmon swap (tofu) is soy, so the Dietitian must
    REJECT it on re-verify; the Shopper falls back to a safe alternative (cod)."""
    r = _recipe("salmon-quinoa-bowl")
    soy = _profile(allergies=["soy"])
    plan = Shopper().plan(r, Pantry(), soy, budget_per_serving=3.0)

    final = [i.item for i in plan.recipe.ingredients]
    assert "tofu" not in final                                        # never applied
    assert any(s.replacement == "tofu" and not s.verified             # attempted + rejected
               for s in plan.rejected_substitutions)
    # whatever the Shopper ended up with is still safe for the user
    assert Dietitian().review(plan.recipe, soy).approved is True


def test_shopper_actually_consults_the_dietitian():
    d = Dietitian()
    Shopper(dietitian=d).plan(_recipe("salmon-quinoa-bowl"), Pantry(),
                              _profile(allergies=["soy"]), budget_per_serving=3.0)
    assert len(d.decisions) > 0            # the dependency loop really ran


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} shopper tests passed.")


if __name__ == "__main__":
    _run_standalone()
