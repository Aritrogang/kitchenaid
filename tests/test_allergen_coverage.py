"""Allergen-vocabulary coverage — a safety invariant, not a data audit.

Pins two things so a regression can't silently weaken the gate:
  1. the recognized allergen categories are exactly the US "big 9" (FDA / FASTER Act 2021);
  2. each category is carried by at least one ingredient in the authority table, so the gate
     can actually detect it.

It does NOT certify the ingredient->allergen mapping is correct or complete — that requires
professional review before launch (see docs/ALLERGEN_DATA.md).

Standalone:  python3 tests/test_allergen_coverage.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_DATA = Path(__file__).resolve().parent.parent / "kitchenaid" / "data"
BIG9 = {"milk", "egg", "fish", "shellfish", "tree_nut", "peanut", "wheat", "soy", "sesame"}


def _load(name):
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


def test_vocabulary_is_exactly_the_big_9():
    cats = {k for k in _load("allergens.json") if not k.startswith("_")}
    assert cats == BIG9, f"allergen vocabulary drifted from the big 9: {cats ^ BIG9}"


def test_every_category_is_detectable():
    ingredients = _load("ingredients.json")
    carried = set()
    for key, val in ingredients.items():
        if key.startswith("_") or not isinstance(val, dict):
            continue
        carried.update(val.get("allergens", []))
    missing = BIG9 - carried
    assert not missing, f"no ingredient carries these allergens, so the gate can't flag them: {missing}"


def test_no_ingredient_declares_an_unknown_allergen():
    vocab = {k for k in _load("allergens.json") if not k.startswith("_")}
    for key, val in _load("ingredients.json").items():
        if key.startswith("_") or not isinstance(val, dict):
            continue
        for a in val.get("allergens", []):
            assert a in vocab, f"ingredient {key!r} declares unknown allergen {a!r}"


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} allergen-coverage tests passed.")


if __name__ == "__main__":
    _run_standalone()
