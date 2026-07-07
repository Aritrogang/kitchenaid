"""Feedback → visible change tests (the two gaps).

Gap 1: Creative mode must be taste-aware — feedback should shape AI-invented dishes,
       not just corpus dishes — WITHOUT ever letting taste resurface an unsafe dish.
Gap 2: The learned change must be legible — the Taster names the lever it pulled, and the
       next meal's `why` says why the pick fits what you taught it.

Standalone:  python3 tests/test_feedback_visibility.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import tools  # noqa: E402
from kitchenaid.agent import Recommendation  # noqa: E402
from kitchenaid.concierge import AgentOptions, Concierge  # noqa: E402
from kitchenaid.models import Ingredient, Moment, Profile, Recipe  # noqa: E402
from kitchenaid.taste import TasteMemory  # noqa: E402

OMNIVORE = {"user_id": "u", "name": "U", "allergies": [], "diet": "none", "budget_per_meal_usd": 8.0}
PEANUT = {"user_id": "u", "name": "U", "allergies": ["peanut"], "diet": "vegetarian"}


def _mk(name, cuisine="", spice=0, item="white rice"):
    return Recipe(id=name, name=name, cuisine=cuisine, time_min=20, servings=2, skill="beginner",
                  equipment=[], diet_tags=[], spice_level=spice, ingredients=[Ingredient(item, 100)])


# --- Gap 1: creative mode is taste-aware ------------------------------------------------

def test_creative_selection_respects_taste(monkeypatch):
    """Two SAFE inventions; learned taste favors one cuisine. The taste-preferred safe dish
    is served — proving feedback now shapes creative dishes, not just corpus ones."""
    import kitchenaid.concierge as C

    def fake_gen(profile, moment, n=6, model=None, hint=None):
        return [_mk("Italian Bowl", "Italian"), _mk("Mexican Bowl", "Mexican")]

    monkeypatch.setattr(C.chef, "generate_recipes", fake_gen)
    conc = C.Concierge()
    taste = TasteMemory(cuisine={"Mexican": 1.0})   # you've loved Mexican before
    r = conc.handle("something for dinner", Profile.from_dict(OMNIVORE),
                    taste=taste, options=AgentOptions(creative_chef=True))
    assert r.used_llm is True
    assert r.recommendation.chosen.name == "Mexican Bowl"   # taste chose among safe inventions
    assert any(e.action == "rank" for e in r.trace)         # and it's logged in the trace


def test_creative_taste_never_overrides_safety(monkeypatch):
    """Taste STRONGLY favors peanut, but peanut is an allergen. The gate removes it from the
    approved set, so taste ranks only among safe dishes and can never resurface it."""
    import kitchenaid.concierge as C

    def fake_gen(profile, moment, n=6, model=None, hint=None):
        return [_mk("Peanut Bowl", "Thai", item="peanut butter"),
                _mk("Rice Bowl", "Thai", item="white rice")]

    monkeypatch.setattr(C.chef, "generate_recipes", fake_gen)
    conc = C.Concierge()
    taste = TasteMemory(ingredient={"peanut butter": 5.0})   # taste loves peanut...
    r = conc.handle("dinner", Profile.from_dict(PEANUT),
                    taste=taste, options=AgentOptions(creative_chef=True))
    # ...but safety wins: the peanut dish never comes back, whatever taste prefers.
    assert r.recommendation.chosen.name == "Rice Bowl"
    items = " ".join(i.item for i in r.recommendation.chosen.ingredients)
    assert "peanut" not in items


def test_pick_by_taste_is_stable_without_learning():
    """No taste yet -> keep the Dietitian's first-approved (deterministic, no reordering)."""
    approved = [(_mk("A"), None), (_mk("B"), None)]
    assert Concierge._pick_by_taste(approved, None) is approved[0]


# --- Gap 2a: the Taster names the lever it pulled ---------------------------------------

def test_feedback_reply_names_the_effect():
    conc = Concierge()
    prof, taste = Profile.from_dict(OMNIVORE), TasteMemory()
    conc.handle("quick dinner", prof, taste=taste, options=AgentOptions())   # sets last meal
    r = conc.handle("that was too spicy", prof, taste=taste, options=AgentOptions(taster=True))
    assert r.intent == "feedback"
    assert "rank spicy dishes lower" in r.message.lower()   # concrete effect, not just a tag


def test_feedback_reply_combines_multiple_effects():
    conc = Concierge()
    prof, taste = Profile.from_dict(OMNIVORE), TasteMemory()
    conc.handle("quick dinner", prof, taste=taste, options=AgentOptions())
    r = conc.handle("loved it but it took too long", prof, taste=taste,
                    options=AgentOptions(taster=True))
    m = r.message.lower()
    assert "lean toward dishes like that" in m and "favor quicker recipes" in m


# --- Gap 2b: the next pick explains itself (TasteMemory.explain) -------------------------

def test_explain_is_none_when_nothing_learned():
    assert TasteMemory().explain(_mk("Anything", "Thai", spice=2)) is None


def test_explain_credits_milder_only_when_dish_is_mild():
    taste = TasteMemory(spice_tolerance=-1.0)
    assert "milder" in (taste.explain(_mk("Mild", spice=0)) or "")
    # honest guard: never claim "milder" for a dish that is itself spicy
    assert "milder" not in (taste.explain(_mk("Spicy", spice=3)) or "")


def test_why_surfaces_the_taste_reason():
    """End to end on the property the UI renders: after 'too spicy', a mild dish's `why`
    leads with the learned reason."""
    taste = TasteMemory(spice_tolerance=-1.0)
    mild = _mk("Mild Veg Bowl", "Thai", spice=0)
    gate = tools.gate(mild, Profile.from_dict(OMNIVORE))
    rec = Recommendation(query="", moment=Moment(), chosen=mild, chosen_gate=gate, taste=taste)
    assert rec.why and "milder" in rec.why[0]


def _run_standalone():
    import types
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and isinstance(fn, types.FunctionType):
            if "monkeypatch" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                continue  # needs pytest; run via pytest for these
            fn()
            print(f"  ok  {name}")
            passed += 1
    print(f"\n{passed} non-monkeypatch tests passed (run `pytest` for the full set).")


if __name__ == "__main__":
    _run_standalone()
