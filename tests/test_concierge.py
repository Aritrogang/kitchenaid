"""Phase 5 tests — the Concierge orchestrator: intent routing, the cost-governor fast path,
session memory for feedback, the observability trace, and safety preserved end to end.

Standalone:  python3 tests/test_concierge.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.concierge import Concierge  # noqa: E402
from kitchenaid.models import Profile  # noqa: E402
from kitchenaid.taste import TasteMemory  # noqa: E402


def _profile(**kw) -> Profile:
    base = dict(user_id="t", name="t", allergies=[], diet="none", budget_per_meal_usd=8.0)
    base.update(kw)
    return Profile.from_dict(base)


# --- intent classification -----------------------------------------------------------

def test_intent_classification():
    c = Concierge()
    assert c.classify("what should I make tonight?") == "quick_dinner"
    assert c.classify("help me use up the fridge") == "use_fridge"
    assert c.classify("what do I need to buy for dinner") == "shopping"
    assert c.classify("plan my week") == "plan_week"
    assert c.classify("that was too spicy") == "feedback"


# --- the cost governor: don't spin up the whole team for a simple turn ---------------

def test_fast_path_uses_two_agents_no_shopper_no_llm():
    c = Concierge()
    r = c.handle("quick dinner", _profile())
    assert r.intent == "quick_dinner"
    assert r.agents_used == 2          # Chef + Dietitian only
    assert r.shopping is None          # Shopper NOT engaged
    assert r.used_llm is False


def test_shopping_intent_engages_the_shopper():
    c = Concierge()
    r = c.handle("what do I need to buy for dinner", _profile())
    assert r.intent == "shopping"
    assert r.agents_used == 3          # Chef + Dietitian + Shopper
    assert r.shopping is not None


# --- session memory + feedback loop --------------------------------------------------

def test_feedback_updates_taste_for_the_last_meal():
    c = Concierge()
    taste = TasteMemory()
    c.handle("what's for dinner", _profile(), taste=taste)   # sets last_recipe
    assert c.last_recipe is not None
    before = taste.spice_tolerance
    r = c.handle("honestly that was too spicy", _profile(), taste=taste)
    assert r.intent == "feedback"
    assert taste.spice_tolerance < before                    # the Taster learned


def test_feedback_without_a_meal_is_graceful():
    c = Concierge()
    r = c.handle("that was too spicy", _profile(), taste=TasteMemory())
    assert r.intent == "feedback" and r.agents_used == 0     # nothing to learn from yet


# --- observability + safety ----------------------------------------------------------

def test_trace_records_the_handoffs():
    c = Concierge()
    r = c.handle("dinner with rice", _profile())
    agents = [e.agent for e in r.trace]
    assert "Concierge" in agents and "Chef" in agents and "Dietitian" in agents


def test_safety_preserved_through_the_concierge():
    c = Concierge()
    r = c.handle("something with noodles", _profile(allergies=["peanut"], diet="vegetarian"))
    if r.recommendation and r.recommendation.chosen:
        names = " ".join(i.item.lower() for i in r.recommendation.chosen.ingredients)
        assert "peanut" not in names


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} concierge tests passed.")


if __name__ == "__main__":
    _run_standalone()
