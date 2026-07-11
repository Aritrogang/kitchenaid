"""Ship-phase tests — the HTTP API layer.

Most coverage is at the KitchenaidService level (the whole agent team + persistence, minus
HTTP). A TestClient smoke test exercises the real FastAPI routing on top. The safety guarantee
must survive all the way out to the API boundary.

Standalone:  python3 tests/test_api.py
"""

import os
import sys
import tempfile
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.api import KitchenaidService, ProfileRequired  # noqa: E402
from kitchenaid.models import Profile  # noqa: E402
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


# --- server-side profile persistence -------------------------------------------------

def test_profile_to_dict_round_trips():
    p = Profile.from_dict(PEANUT_VEG)
    assert Profile.from_dict(p.to_dict()).to_dict() == p.to_dict()


def test_chat_persists_profile_then_it_can_be_omitted():
    svc = _service()
    svc.chat("p1", "quick dinner", PEANUT_VEG)                  # profile sent -> stored server-side
    assert svc.get_profile("p1")["allergies"] == ["peanut"]
    # A later turn omits the profile; the stored peanut allergy must still gate the meal.
    out = svc.chat("p1", "something with noodles")             # no profile argument at all
    if out["meal"]:
        assert not any("peanut" in i["item"].lower() for i in out["meal"]["ingredients"])


def test_chat_without_profile_and_none_stored_raises():
    with pytest.raises(ProfileRequired):
        _service().chat("nobody", "quick dinner")             # nothing sent, nothing stored


def test_put_profile_is_authoritative_on_user_id():
    svc = _service()
    saved = svc.put_profile("p2", {"name": "Sam", "allergies": ["Sesame"], "diet": "Vegan"})
    assert saved["user_id"] == "p2"                            # path wins even without it in the body
    assert saved["allergies"] == ["sesame"] and saved["diet"] == "vegan"   # normalized
    assert svc.get_profile("p2") == saved


def test_http_profile_endpoints_and_omitted_profile():
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    ghost = f"ghost-{uuid.uuid4()}"
    webby = f"web-{uuid.uuid4()}"

    assert client.get(f"/profile/{webby}").status_code == 404          # nothing stored yet

    put = client.put(f"/profile/{webby}",
                     json={"name": "Web", "allergies": ["peanut"], "diet": "vegetarian"})
    assert put.status_code == 200 and put.json()["allergies"] == ["peanut"]
    assert client.get(f"/profile/{webby}").json()["diet"] == "vegetarian"

    # chat may now omit profile; the stored peanut allergy still gates at the HTTP boundary
    r = client.post("/chat", json={"user_id": webby, "query": "noodles please"})
    assert r.status_code == 200
    meal = r.json()["meal"]
    if meal:
        assert not any("peanut" in i["item"].lower() for i in meal["ingredients"])

    # a user with no stored profile and none in the request -> 400, not a crash
    assert client.post("/chat", json={"user_id": ghost, "query": "quick dinner"}).status_code == 400


def test_every_answer_carries_the_safety_disclaimer():
    out = _service().chat("d1", "quick dinner", OMNIVORE)
    assert "disclaimer" in out
    d = out["disclaimer"].lower()
    assert "read the packaging" in d and "medical" in d      # never imply a safety guarantee


def test_forget_erases_profile_and_taste():
    svc = _service()
    svc.chat("f1", "quick dinner", PEANUT_VEG)                # stores the profile
    svc.chat("f1", "that was too spicy", PEANUT_VEG)          # learns some taste
    assert svc.get_profile("f1") is not None
    assert svc.keeper.load_taste("f1").spice_tolerance < 0
    assert svc.forget("f1")["deleted"] is True
    assert svc.get_profile("f1") is None                      # profile gone
    assert svc.keeper.load_taste("f1").spice_tolerance == 0.0  # taste back to fresh


def test_http_delete_profile_is_right_to_erasure():
    from fastapi.testclient import TestClient
    from kitchenaid.api import app
    client = TestClient(app)
    u = f"del-{uuid.uuid4()}"
    client.put(f"/profile/{u}", json={"allergies": ["peanut"], "diet": "vegetarian"})
    assert client.get(f"/profile/{u}").status_code == 200
    assert client.delete(f"/profile/{u}").json()["deleted"] is True
    assert client.get(f"/profile/{u}").status_code == 404     # nothing left


def test_last_meal_survives_a_fresh_service_instance():
    # Serverless simulation: two independent services sharing a store dir but NO shared memory.
    store_dir = tempfile.mkdtemp()
    svc1 = KitchenaidService(ProfileKeeper(store_dir))
    svc1.chat("s1", "quick dinner", OMNIVORE)                 # meal -> last recipe persisted
    svc2 = KitchenaidService(ProfileKeeper(store_dir))        # cold start: empty in-memory sessions
    out = svc2.chat("s1", "that was too spicy", OMNIVORE)     # feedback on the fresh instance
    assert out["intent"] == "feedback"
    assert "rank spicy dishes lower" in out["message"].lower()    # attached to the persisted meal
    assert svc2.keeper.load_taste("s1").spice_tolerance < 0       # and the taste actually moved


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} api tests passed.")


if __name__ == "__main__":
    _run_standalone()
