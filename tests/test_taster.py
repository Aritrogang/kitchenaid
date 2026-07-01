"""Phase 4 tests — taste memory + the Taster feedback loop.

The point of Phase 4 is that the system stops being static: feedback moves numbers, and the
Chef's ranking moves with them. These pin that the loop actually closes, and that taste
persists (the Profile Keeper's job).

Standalone:  python3 tests/test_taster.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import chef, data  # noqa: E402
from kitchenaid.models import Moment, Profile  # noqa: E402
from kitchenaid.profile_keeper import ProfileKeeper  # noqa: E402
from kitchenaid.taste import TasteMemory  # noqa: E402
from kitchenaid.taster import Taster  # noqa: E402


def _recipe(rid):
    return next(r for r in data.recipes() if r.id == rid)


def _profile(**kw) -> Profile:
    base = dict(user_id="t", name="t", allergies=[], diet="none")
    base.update(kw)
    return Profile.from_dict(base)


# --- feedback moves the numbers ------------------------------------------------------

def test_loved_boosts_score_and_rank():
    mem = TasteMemory()
    curry = _recipe("chickpea-spinach-curry")
    assert mem.score(curry) == 0.0
    Taster().record(curry, "loved", mem)
    assert mem.score(curry) > 0
    assert mem.cuisine["Indian"] > 0 and curry.name in mem.loved
    # the Chef ranks it at least as high as without taste (usually higher)
    profile, moment = _profile(), Moment()
    with_taste = chef.propose(profile, moment, taste=mem)
    without = chef.propose(profile, moment)
    assert with_taste.index(curry) <= without.index(curry)


def test_disliked_lowers_score():
    mem = TasteMemory()
    r = _recipe("shrimp-fried-rice")
    Taster().record(r, "disliked", mem)
    assert mem.score(r) < 0 and r.name in mem.disliked


def test_too_spicy_penalizes_spicy_dishes_only():
    mem = TasteMemory()
    spicy = _recipe("chickpea-spinach-curry")     # spice_level 2
    mild = _recipe("veggie-omelette")             # spice_level 0
    Taster().record(spicy, "too spicy", mem)
    assert mem.spice_tolerance < 0
    assert mem.score(spicy) < 0                    # spicy dish now penalized
    assert mem.score(mild) == 0.0                  # spice-0 dish untouched


def test_too_long_penalizes_slow_dishes():
    mem = TasteMemory()
    slow = _recipe("lentil-soup")                  # 35 min
    Taster().record(slow, "too long", mem)
    assert mem.time_pref < 0 and mem.score(slow) < 0


def test_multiple_tags_at_once():
    mem = TasteMemory()
    Taster().record(_recipe("chickpea-spinach-curry"), ["loved", "too spicy"], mem)
    assert mem.cuisine["Indian"] > 0 and mem.spice_tolerance < 0


# --- persistence (the Profile Keeper) ------------------------------------------------

def test_taste_memory_roundtrip():
    mem = TasteMemory()
    Taster().record(_recipe("chickpea-spinach-curry"), "loved", mem)
    path = tempfile.mktemp(suffix=".json")
    mem.save(path)
    back = TasteMemory.load(path)
    assert back.cuisine == mem.cuisine and back.loved == mem.loved


def test_profile_keeper_persists_taste_across_loads():
    pk = ProfileKeeper(tempfile.mkdtemp())
    mem = pk.load_taste("u1")                       # fresh
    Taster().record(_recipe("chickpea-spinach-curry"), "loved", mem)
    pk.save_taste("u1", mem)
    reloaded = pk.load_taste("u1")
    assert reloaded.loved == ["Chickpea & Spinach Curry"]
    assert reloaded.cuisine.get("Indian", 0) > 0


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} taster tests passed.")


if __name__ == "__main__":
    _run_standalone()
