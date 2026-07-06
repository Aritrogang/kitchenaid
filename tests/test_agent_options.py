"""Agent-toggle tests — the user can turn team members on/off, EXCEPT the Dietitian.

The absence of a Dietitian toggle is the design: safety is structural, not configurable.
These pin that the toggles do what the UI promises, and that no combination of options
weakens the gate.

Standalone:  python3 tests/test_agent_options.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.api import KitchenaidService  # noqa: E402
from kitchenaid.concierge import AGENT_TEAM, AgentOptions, Concierge  # noqa: E402
from kitchenaid.models import Profile  # noqa: E402
from kitchenaid.profile_keeper import ProfileKeeper  # noqa: E402
from kitchenaid.taste import TasteMemory  # noqa: E402

OMNIVORE = {"user_id": "u", "name": "U", "allergies": [], "diet": "none", "budget_per_meal_usd": 8.0}
PEANUT = {"user_id": "u", "name": "U", "allergies": ["peanut"], "diet": "vegetarian"}


def _svc():
    return KitchenaidService(ProfileKeeper(tempfile.mkdtemp()))


# --- the Dietitian is structurally un-toggleable --------------------------------------

def test_dietitian_has_no_toggle():
    assert not hasattr(AgentOptions(), "dietitian")
    meta = next(a for a in AGENT_TEAM if a["id"] == "dietitian")
    assert meta["toggleable"] is False and "safety" in meta["always_on_reason"].lower()


def test_no_option_combo_bypasses_the_gate():
    """Whatever the toggles, an allergen never comes back. Keyless: config auto-loads .env,
    so pop the key or creative=True would make real (slow, paid) API calls inside unit tests.
    The live creative path is exercised deliberately in browser testing, not here."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    for creative in (False, True):           # keyless -> creative falls back to corpus
        for shopper in (False, True):
            out = _svc().chat("u", "something with noodles", PEANUT,
                              options={"creative_chef": creative, "shopper": shopper})
            if out["meal"]:
                items = [i["item"].lower() for i in out["meal"]["ingredients"]]
                assert not any("peanut" in it for it in items)


# --- shopper toggle --------------------------------------------------------------------

def test_shopper_off_suppresses_grocery_list():
    out = _svc().chat("u", "what do I need to buy for dinner", OMNIVORE,
                      options={"shopper": False})
    assert out["intent"] == "shopping"
    assert out["grocery"] is None
    assert "Shopper is off" in out["message"]


def test_shopper_on_by_default():
    out = _svc().chat("u", "what do I need to buy for dinner", OMNIVORE, options={})
    assert out["grocery"] is not None


# --- taster toggle -----------------------------------------------------------------------

def test_taster_off_means_no_learning():
    svc = _svc()
    svc.chat("u1", "quick dinner", OMNIVORE)
    before = svc.keeper.load_taste("u1").spice_tolerance
    out = svc.chat("u1", "that was too spicy", OMNIVORE, options={"taster": False})
    assert "learning is switched off" in out["message"]
    assert svc.keeper.load_taste("u1").spice_tolerance == before   # unchanged


def test_taster_on_learns():
    svc = _svc()
    svc.chat("u2", "quick dinner", OMNIVORE)
    out = svc.chat("u2", "that was too spicy", OMNIVORE, options={"taster": True})
    assert out["intent"] == "feedback"
    assert svc.keeper.load_taste("u2").spice_tolerance < 0


# --- creative chef toggle (keyless behavior: graceful fallback) --------------------------

def test_all_blocked_triggers_repropose_loop(monkeypatch):
    """When the Dietitian blocks EVERY invented dish, the Concierge feeds the reasons back to
    the Chef and regenerates once. This path (previously uncovered) crashed on a missing
    helper — pin it with a stub generator so no API/key is needed."""
    import kitchenaid.concierge as C
    from kitchenaid.models import Ingredient, Moment, Recipe

    def _mk(rid, item):
        return Recipe(id=rid, name=rid, cuisine="", time_min=20, servings=2, skill="beginner",
                      equipment=[], diet_tags=[], spice_level=0, ingredients=[Ingredient(item, 100)])

    calls = {"n": 0}

    def fake_generate(profile, moment, n=6, model=None, hint=None):
        calls["n"] += 1
        # first batch: all peanut (blocked); second batch (after repropose): safe
        return [_mk("bad", "peanut butter")] if calls["n"] == 1 else [_mk("good", "chickpeas")]

    monkeypatch.setattr(C.chef, "generate_recipes", fake_generate)
    conc = C.Concierge()
    r = conc.handle("noodles", Profile.from_dict(PEANUT),
                    taste=TasteMemory(), options=AgentOptions(creative_chef=True))
    assert calls["n"] == 2                                   # it reproposed once
    assert r.recommendation.chosen is not None               # safe dish on the retry
    assert "peanut" not in " ".join(i.item for i in r.recommendation.chosen.ingredients)
    assert any(e.action == "regenerate" for e in r.trace)


def test_creative_without_key_falls_back_to_corpus():
    os.environ.pop("ANTHROPIC_API_KEY", None)   # ensure keyless in this process
    c = Concierge()
    r = c.handle("korean-inspired dinner, extra protein", Profile.from_dict(OMNIVORE),
                 taste=TasteMemory(), options=AgentOptions(creative_chef=True))
    assert r.used_llm is False                   # fell back, honestly reported
    assert any("falling back" in e.detail for e in r.trace if e.agent == "Chef")


# --- /agents metadata --------------------------------------------------------------------

def test_agents_endpoint_serves_the_team():
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    body = TestClient(app).get("/agents").json()
    ids = [a["id"] for a in body["agents"]]
    assert ids == ["concierge", "chef", "dietitian", "shopper", "profile_keeper", "taster"]
    toggleable = {a["id"] for a in body["agents"] if a["toggleable"]}
    assert toggleable == {"chef", "shopper", "taster"}


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} agent-option tests passed.")


if __name__ == "__main__":
    _run_standalone()
