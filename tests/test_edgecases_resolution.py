"""Edge-case regression tests — adversarial ingredient strings through resolution + gate.

Attack thesis: the only way the allergen gate can approve an unsafe meal is if resolution
maps a free-text string to a canonical entry whose attrs UNDERSTATE the truth. So we hammer
resolve()/classify() with decoration, unicode, homoglyphs, whitespace tricks, compounds and
modifier evasions, and assert the outcome is always one of:
    (a) resolved to an entry that still carries the real allergen  -> gate blocks, or
    (b) unresolved                                                 -> gate fails closed.

Runs with pytest:  python3 -m pytest tests/test_edgecases_resolution.py -q
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import data, resolution  # noqa: E402
from kitchenaid.models import Ingredient, Profile, Recipe  # noqa: E402
from kitchenaid.tools import gate  # noqa: E402


def _profile(**kw):
    base = dict(user_id="t", name="Test", allergies=[], diet="none")
    base.update(kw)
    return Profile.from_dict(base)


def _synthetic(*items):
    return Recipe(id="synthetic", name="Synthetic", cuisine="", time_min=10, servings=1,
                  skill="beginner", equipment=[], diet_tags=[], spice_level=0,
                  ingredients=[Ingredient(i, 50) for i in items])


# --- plain adversarial strings --------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "",                          # empty
    "   ",                       # whitespace only
    "p e a n u t",               # spaced-out letters
    "notpeanut",                 # no substring fallback allowed
    "peanuts and shrimp",        # compound — must not resolve to either half
    "shrimp and peanuts",        # compound, reversed (exercises trailing-s singularizer)
    "butter milk",               # neither butter nor milk nor buttermilk
    "buttermilk",                # not in the table -> unresolved, never 'butter'+'milk'
    "peanut-free peanut butter", # 'peanut-free' is NOT a known modifier
    "vegan beef",                # free-from path, no canonical entry
    "gluten-free wheat flour",   # free-from path, no canonical entry
    "vegan-butter",              # hyphen defeats the modifier prefix match -> descriptive path
    "veganbutter",               # concatenated
    "dairy-free-butter",         # all-hyphen variant
    "non-dairy milk",            # free-from path, no canonical entry (common-string gap)
    "crème fraîche",             # accents fold, but 'creme fraiche' has no entry
    "花生酱",                     # CJK 'peanut butter' -> normalizes to '' -> unresolved
    "🥜",                        # emoji only
    "🥜 butter",                 # emoji + word -> ' butter'? no: emoji becomes a space
    "реanut butter",             # Cyrillic 'р','е' homoglyphs -> chars dropped, no match
    "pea‍nut butter",       # zero-width joiner splits the word
])
def test_adversarial_strings_are_unresolved(raw):
    res = resolution.resolve(raw)
    assert res.canonical is None, (
        f"{raw!r} resolved to {res.canonical!r} via {res.method} — expected unresolved")


def test_emoji_plus_word_detail():
    """'🥜 butter' — the emoji is replaced by a space, leaving 'butter'. Document the actual
    outcome: it resolves to dairy butter. That is CORRECT for the milk allergen (butter is
    what remains textually) and the peanut emoji carries no textual meaning to the resolver.
    The dangerous direction (emoji hiding an allergen from an allergic user) fails closed
    because '🥜' alone is unresolved."""
    res = resolution.resolve("🥜 butter")
    # pin whichever outcome holds; the safety requirement is only that a peanut-allergic
    # user is never APPROVED for it if it were truly peanut butter — see gate test below.
    assert res.canonical in (None, "butter")


@pytest.mark.parametrize("raw,expected", [
    ("PEANUT BUTTER!!!", "peanut butter"),
    ("  peanut   butter  ", "peanut butter"),
    ("peanut\tbutter", "peanut butter"),
    ("peanut\nbutter", "peanut butter"),
    ("pea!nut butter", None),                 # punctuation becomes a space mid-word
    ("péanut butter", "peanut butter"),       # accent folding cannot hide an allergen
    ("jalapeño", "jalapeno"),
    ("low-sodium peanut butter", "peanut butter"),
    ("peanut butter powder", "peanut butter"),
    ("ground peanuts", "peanuts"),
    ("roasted peanuts", "peanuts"),
    ("peanut butters", "peanut butter"),      # singularize
    ("soy sauces", "soy sauce"),
    ("smoked salmon", "salmon"),
    ("ｖｅｇａｎ　ｂｕｔｔｅｒ", "vegan butter"),  # fullwidth folds TOWARD ascii, keeps modifier
    ("vegan butter!!!", "vegan butter"),
    ("dairy-free cheese", "vegan cheese"),
    ("eggless mayo", "vegan mayo"),
])
def test_resolution_pins(raw, expected):
    assert resolution.resolve(raw).canonical == expected


def test_resolve_none_raises_typeerror():
    """None is not tolerated — resolve(None) raises. Pinned so a future 'graceful' change
    is a conscious decision (silently treating None as unresolved would also be fine)."""
    with pytest.raises(TypeError):
        resolution.resolve(None)


def test_resolve_non_string_raises_typeerror():
    with pytest.raises(TypeError):
        resolution.resolve(42)


# --- the gate consumes the adversarial strings ----------------------------------------

@pytest.mark.parametrize("raw", [
    "PEANUT BUTTER!!!", "péanut butter", "low-sodium peanut butter",
    "peanut butter powder", "ground peanuts", "peanut butters",
    "p e a n u t", "peanuts and shrimp", "реanut butter", "🥜",
    "pea‍nut butter", "notpeanut", "peanut-free peanut butter",
])
def test_peanut_allergic_user_never_gets_peanutish_string_approved(raw):
    """Every decorated/evasive/ambiguous peanut string must block for a peanut-allergic
    user — either it resolves to a peanut-carrying entry, or it fails closed as unresolved."""
    verdict = gate(_synthetic(raw), _profile(allergies=["peanut"]))
    assert verdict.approved is False
    assert verdict.hard_violations


def test_unresolved_ingredient_passes_for_unrestricted_user():
    """SURPRISE (documented current behavior): with NO active hard rule, an unresolvable
    ingredient sails through — it contributes 0 kcal / $0 and produces no flag at all. The
    code comments call this out ('a real system would flag this')."""
    verdict = gate(_synthetic("mystery goo from a jar"), _profile())
    assert verdict.approved is True
    assert verdict.flags == [] or all("mystery" not in f for f in verdict.flags)
    assert verdict.calories_per_serving == 0.0
    assert verdict.cost_per_serving_usd == 0.0


def test_empty_string_ingredient_fails_closed_only_under_hard_rule():
    assert gate(_synthetic(""), _profile(allergies=["milk"])).approved is False
    assert gate(_synthetic(""), _profile(diet="vegan")).approved is False
    # no hard rule -> approved (same surprise as above)
    assert gate(_synthetic(""), _profile()).approved is True


# --- systematic sweeps ----------------------------------------------------------------

_DECORATIONS = [
    lambda s: s,
    lambda s: s.upper(),
    lambda s: "  " + s + "  ",
    lambda s: s + "!!!",
    lambda s: "fresh " + s,
    lambda s: "organic " + s,
    lambda s: "chopped " + s,
    lambda s: s + ", diced",
    lambda s: s.replace("a", "á").replace("e", "é"),   # á é accents
    lambda s: "FRESH " + s.upper() + "!!",
]


def test_decorated_allergen_carriers_never_approved_for_allergic_user():
    """THE core adversarial sweep. For every canonical ingredient that carries an allergen,
    decorate it every way we know and assert the gate never approves it for a user allergic
    to that allergen. Resolution must either land on an entry still carrying the allergen
    or fail closed — losing the allergen through decoration would be CRITICAL."""
    attrs = data.ingredient_attrs()
    checked = 0
    for item, a in attrs.items():
        for allergen in a.get("allergens", []):
            profile = _profile(allergies=[allergen])
            for dec in _DECORATIONS:
                verdict = gate(_synthetic(dec(item)), profile)
                assert verdict.approved is False, (
                    f"gate approved {dec(item)!r} for {allergen}-allergic user")
                checked += 1
    assert checked > 500   # meaningful coverage, not a vacuous loop


def test_decorated_animal_products_never_approved_for_vegan():
    attrs = data.ingredient_attrs()
    profile = _profile(diet="vegan")
    forbidden = set(data.diet_rules()["vegan"]["forbidden_props"])
    for item, a in attrs.items():
        if not (forbidden & set(a.get("diet_props", []))):
            continue
        for dec in _DECORATIONS:
            verdict = gate(_synthetic(dec(item)), profile)
            assert verdict.approved is False, (
                f"gate approved {dec(item)!r} for a vegan user")


def test_modifier_item_sweep_never_misresolves():
    """classify('<modifier> <item>') across every inverting modifier x every canonical item
    and every synonym key must NEVER be 'misresolved' — that is the substring bug in
    disguise, and classify() flags it as critical."""
    modifiers = sorted(resolution._INVERTING_MODIFIERS)
    names = sorted(set(data.ingredient_attrs()) | set(resolution._SYNONYMS))
    for mod in modifiers:
        for name in names:
            c = resolution.classify("{} {}".format(mod, name))
            assert c.outcome != "misresolved", (
                f"CRITICAL: {mod + ' ' + name!r} misresolved to {c.canonical!r}")


def test_every_synonym_target_exists_in_attribute_table():
    """A synonym mapping to a key missing from ingredients.json would resolve but then
    lookup None -> fail closed. Not unsafe, but a data-integrity regression worth pinning."""
    attrs = data.ingredient_attrs()
    for src, dst in resolution._SYNONYMS.items():
        assert dst in attrs, f"synonym {src!r} -> {dst!r} points outside the attr table"
    for src, dst in resolution._FREE_FROM_SYNONYMS.items():
        assert dst in attrs, f"free-from synonym {src!r} -> {dst!r} points outside the table"


def test_free_from_targets_actually_satisfy_their_modifier():
    """Every _FREE_FROM_SYNONYMS target must genuinely exclude what its source's modifier
    promises (violates_modifier is the detector)."""
    for src, dst in resolution._FREE_FROM_SYNONYMS.items():
        mod, _ = resolution.detect_modifier(src)
        if mod is None:
            continue   # e.g. 'plant butter' has no registered modifier prefix; fine
        assert not resolution.violates_modifier(mod, dst), (
            f"{src!r} -> {dst!r} violates its own '{mod}' promise")


# --- pathological input sizes ---------------------------------------------------------

def test_10k_char_string_resolves_quickly_and_fails_closed():
    big = "x" * 10_000
    t0 = time.perf_counter()
    res = resolution.resolve(big)
    dt = time.perf_counter() - t0
    assert res.canonical is None
    assert dt < 2.0, f"resolve on 10k chars took {dt:.2f}s"


def test_qualifier_bomb_terminates_in_reasonable_time():
    """'fresh fresh fresh ... butter' — each _strip_qualifiers pass removes one word, so a
    long chain is O(words x qualifiers x len). Pin that a 200-word bomb still completes
    quickly and STILL resolves to the true base (blocked for a milk-allergic user)."""
    bomb = ("fresh " * 200) + "butter"
    t0 = time.perf_counter()
    res = resolution.resolve(bomb)
    dt = time.perf_counter() - t0
    assert res.canonical == "butter"
    assert dt < 5.0, f"qualifier bomb took {dt:.2f}s"
    verdict = gate(_synthetic(bomb), _profile(allergies=["milk"]))
    assert verdict.approved is False
