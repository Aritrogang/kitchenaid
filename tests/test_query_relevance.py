"""Does the Chef actually listen? — query-relevance ranking.

The deterministic ranker used to score only structured fields (on-hand, time, skill, taste), so
"korean tofu bowl" and "italian pasta" scored identically and returned the same dish. These pin
that the user's own words steer the pick — and that relevance can never override the gate.

Standalone:  python3 tests/test_query_relevance.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import agent  # noqa: E402
from kitchenaid.chef import _query_relevance, _query_terms  # noqa: E402
from kitchenaid.models import Profile  # noqa: E402

OMNIVORE = {"user_id": "u", "name": "U", "allergies": [], "diet": "none"}
PEANUT = {"user_id": "u", "name": "U", "allergies": ["peanut"], "diet": "none"}


def _pick(query, profile=OMNIVORE):
    return agent.recommend(query, Profile.from_dict(profile)).chosen


# --- the core regression: different requests -> different, relevant dishes -------------

def test_distinct_requests_give_distinct_dishes():
    names = {_pick(q).name for q in (
        "creamy italian pasta with mushrooms",
        "korean spicy tofu rice bowl",
        "light thai coconut soup",
        "mexican black bean tacos",
        "a greek salad",
    )}
    assert len(names) == 5, f"requests collapsed to the same dish: {names}"


def test_cuisine_request_is_honored():
    for query, cuisine in [("italian pasta", "Italian"), ("thai curry", "Thai"),
                           ("a greek salad", "Greek"), ("indian lentil curry", "Indian"),
                           ("korean rice bowl", "Korean")]:
        got = _pick(query)
        assert got.cuisine == cuisine, f"{query!r} -> {got.name} [{got.cuisine}], wanted {cuisine}"


def test_named_ingredient_is_honored():
    assert "salmon" in " ".join(i.item for i in _pick("something with salmon").ingredients)


# --- relevance must never beat the safety gate ---------------------------------------

def test_relevance_cannot_override_an_allergen():
    # Ask *directly* for the peanut dish while allergic — ranking may prefer it, the gate wins.
    chosen = _pick("spicy peanut noodles with extra peanuts", PEANUT)
    if chosen is not None:
        items = " ".join(i.item.lower() for i in chosen.ingredients)
        assert "peanut" not in items


# --- the helper ----------------------------------------------------------------------

def test_stopwords_dropped_and_plurals_matched():
    terms = _query_terms("something quick for dinner with tacos")
    assert "quick" not in terms and "dinner" not in terms      # no dish signal
    assert "tacos" in terms and "taco" in terms                # crude singular for matching


def test_empty_query_is_neutral():
    recipe = _pick("quick dinner")
    assert _query_relevance(recipe, "") == 0.0


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} query-relevance tests passed.")


if __name__ == "__main__":
    _run_standalone()
