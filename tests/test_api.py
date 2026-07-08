"""Ship-phase tests — the HTTP API layer.

Most coverage is at the KitchenaidService level (the whole agent team + persistence, minus
HTTP). A TestClient smoke test exercises the real FastAPI routing on top. The safety guarantee
must survive all the way out to the API boundary.

Standalone:  python3 tests/test_api.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.api import KitchenaidService  # noqa: E402
from kitchenaid.profile_keeper import ProfileKeeper  # noqa: E402

OMNIVORE = {"user_id": "u", "name": "U", "allergies": [], "diet": "none", "budget_per_meal_usd": 8.0}
PEANUT_VEG = {"user_id": "u", "name": "U", "allergies": ["peanut"], "diet": "vegetarian"}


def _service():
    return KitchenaidService(ProfileKeeper(tempfile.mkdtemp()))


# --- the service (whole team behind one call) ----------------------------------------

def test_chat_suggests_a_meal():
    out = _service().chat("u1", "quick dinner", OMNIVORE)
    assert out["intent"] == "quick_dinner"
    assert out["meal"] is not None and out["grocery"] is None      # cost governor: no Shopper
    assert out["agents_used"] == 2 and out["used_llm"] is False


def test_shopping_returns_a_grocery_list():
    out = _service().chat("u2", "what do I need to buy for dinner with rice", OMNIVORE)
    assert out["intent"] == "shopping"
    assert out["grocery"] is not None and out["grocery"]["total_cost_usd"] > 0
    assert out["agents_used"] == 3


def test_api_never_returns_an_allergen():
    out = _service().chat("u3", "something with noodles", PEANUT_VEG)
    if out["meal"]:
        items = [i["item"].lower() for i in out["meal"]["ingredients"]]
        assert not any("peanut" in it for it in items)


def test_feedback_persists_taste_across_turns():
    svc = _service()
    svc.chat("u4", "what's for dinner", OMNIVORE)                   # sets last meal (session)
    before = svc.keeper.load_taste("u4").spice_tolerance
    out = svc.chat("u4", "honestly that was too spicy", OMNIVORE)
    assert out["intent"] == "feedback"
    assert svc.keeper.load_taste("u4").spice_tolerance < before     # persisted by Profile Keeper


def test_response_carries_the_trace():
    out = _service().chat("u5", "dinner with rice", OMNIVORE)
    agents = [e["agent"] for e in out["trace"]]
    assert "Concierge" in agents and "Chef" in agents and "Dietitian" in agents


# --- the real HTTP boundary (FastAPI TestClient) -------------------------------------

def test_http_health_and_chat():
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)

    assert client.get("/health").json()["status"] == "ok"

    r = client.post("/chat", json={"user_id": "h1", "query": "quick dinner", "profile": OMNIVORE})
    assert r.status_code == 200
    body = r.json()
    assert body["meal"] is not None and body["intent"] == "quick_dinner"

    # safety survives the HTTP boundary
    r2 = client.post("/chat", json={"user_id": "h2", "query": "noodles please", "profile": PEANUT_VEG})
    meal = r2.json()["meal"]
    if meal:
        assert not any("peanut" in i["item"].lower() for i in meal["ingredients"])


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} api tests passed.")


if __name__ == "__main__":
    _run_standalone()
