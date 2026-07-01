"""Phase 2 tests — the Dietitian agent boundary.

The safety guarantee must now hold at the AGENT level: the Chef proposes, but only the
Dietitian can approve, and it can never approve an allergen. These re-assert the invariant
across the propose->verify handoff, not just the raw gate.

Standalone:  python3 tests/test_dietitian.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import agent, data  # noqa: E402
from kitchenaid.dietitian import Dietitian, Review  # noqa: E402
from kitchenaid.models import Ingredient, Profile, Recipe  # noqa: E402


def _profile(**kw) -> Profile:
    base = dict(user_id="t", name="Test", allergies=[], diet="none")
    base.update(kw)
    return Profile.from_dict(base)


def _recipe(rid):
    return next(r for r in data.recipes() if r.id == rid)


# --- the agent is a real verifier -----------------------------------------------------

def test_review_returns_verdict_and_logs_decision():
    d = Dietitian()
    v = d.review(_recipe("lentil-soup"), _profile(diet="vegan"))
    assert v.approved is True
    assert len(d.decisions) == 1 and d.decisions[0] is v


def test_review_batch_picks_first_approved_and_collects_rejected():
    d = Dietitian()
    profile = _profile(diet="vegan")
    review = d.review_batch(data.recipes(), profile)
    assert isinstance(review, Review)
    assert review.considered == len(data.recipes())
    if review.chosen is not None:
        assert review.verdict.approved is True
    # everything in rejected genuinely failed a hard rule
    for _, verdict in review.rejected:
        assert verdict.approved is False and verdict.hard_violations


# --- the safety boundary holds at the agent level ------------------------------------

def test_dietitian_never_approves_an_allergen():
    """Hand the WHOLE corpus to a peanut-allergic user's Dietitian: nothing it approves may
    contain peanut, and the peanut dish must land in rejected."""
    d = Dietitian()
    profile = _profile(allergies=["peanut"], diet="vegetarian")
    review = d.review_batch(data.recipes(), profile)
    if review.chosen:
        names = " ".join(i.item.lower() for i in review.chosen.ingredients)
        assert "peanut" not in names
    assert any(r.id == "peanut-noodles" for r, _ in review.rejected)


def test_no_safe_candidate_yields_no_choice():
    """If every candidate violates a hard rule, the Dietitian approves nothing."""
    d = Dietitian()
    # a vegan user handed only an all-meat candidate
    meaty = Recipe(id="m", name="Meat Plate", cuisine="", time_min=10, servings=1,
                   skill="beginner", equipment=[], diet_tags=[], spice_level=0,
                   ingredients=[Ingredient("beef", 200), Ingredient("bacon", 50)])
    review = d.review_batch([meaty], _profile(diet="vegan"))
    assert review.chosen is None and len(review.rejected) == 1


# --- the refactored agent loop still routes safely through the Dietitian --------------

def test_agent_recommend_routes_through_dietitian():
    profile = _profile(allergies=["peanut"], diet="vegetarian")
    rec = agent.recommend("something with noodles, quick", profile)
    if rec.chosen:
        names = " ".join(i.item.lower() for i in rec.chosen.ingredients)
        assert "peanut" not in names
    assert any(r.id == "peanut-noodles" for r, _ in rec.rejected)


def test_agent_accepts_injected_dietitian():
    d = Dietitian()
    agent.recommend("quick dinner", _profile(), dietitian=d)
    assert len(d.decisions) > 0   # the injected verifier actually did the work


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} dietitian tests passed.")


if __name__ == "__main__":
    _run_standalone()
