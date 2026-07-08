"""Eval harness (Phase 6) — constraint-satisfaction first.

Replays a frozen corpus of REAL generated dishes (eval/fixtures/real_dishes.json) against a
spread of profiles and reports:

  * SAFETY (hard, must be perfect): mis-resolutions and unsafe approvals must both be ZERO.
    An "unsafe approval" is re-derived INDEPENDENTLY from the ingredient-attribute table — if
    the gate approved a dish that actually carries one of the profile's allergens (or a
    diet-forbidden property), that's a hole. This is the property the whole project ships on.
  * COVERAGE (soft, tracked with a floor): fraction of real ingredient strings that resolve.
    A floor turns a resolver regression (like the "extra virgin" bug) into a test failure.
  * APPROVAL rate (soft, usability signal).

The generated half of the eval lives in tests/test_gate_properties.py (Hypothesis fuzzing);
this is the frozen-real-fixtures half. Together they are the eval harness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import data, resolution
from .models import Ingredient, Profile, Recipe
from .tools import gate

_FIXTURES = Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "real_dishes.json"

# The gate must never approve an unsafe dish for ANY of these. Spread across allergens + diets.
EVAL_PROFILES = [
    {"user_id": "e1", "name": "omnivore", "allergies": [], "diet": "none"},
    {"user_id": "e2", "name": "vegan+milk", "allergies": ["milk"], "diet": "vegan"},
    {"user_id": "e3", "name": "peanut", "allergies": ["peanut"], "diet": "none"},
    {"user_id": "e4", "name": "shellfish/pescatarian", "allergies": ["shellfish"], "diet": "pescatarian"},
    {"user_id": "e5", "name": "gluten-free", "allergies": ["wheat"], "diet": "none"},
    {"user_id": "e6", "name": "tree-nut+peanut/vegetarian", "allergies": ["tree_nut", "peanut"], "diet": "vegetarian"},
    {"user_id": "e7", "name": "sesame", "allergies": ["sesame"], "diet": "none"},
]

# Freeze a coverage floor (achieved 97.6%) — a resolver regression that drops below this
# fails the build. Headroom left so adding a fixture with a long-tail miss isn't brittle.
COVERAGE_FLOOR = 0.90


@dataclass
class EvalReport:
    dishes: int
    profiles: int
    ingredient_strings: int
    resolved: int
    coverage: float
    misresolved: int          # MUST be 0
    approvals: int
    approval_rate: float
    unsafe_approvals: int      # MUST be 0
    unsafe_examples: list

    @property
    def safe(self) -> bool:
        return self.misresolved == 0 and self.unsafe_approvals == 0

    @property
    def passes(self) -> bool:
        return self.safe and self.coverage >= COVERAGE_FLOOR


def _load(path: str | Path | None = None) -> list[dict]:
    p = Path(path) if path else _FIXTURES
    return json.loads(p.read_text(encoding="utf-8"))["dishes"]


def _to_recipe(dish: dict) -> Recipe:
    return Recipe(id="fx", name=dish["name"], cuisine="", time_min=20, servings=2,
                  skill="beginner", equipment=[], diet_tags=[], spice_level=0,
                  ingredients=[Ingredient(s, 100) for s in dish["ingredients"]])


def _carries_violation(recipe: Recipe, profile: Profile) -> str | None:
    """Independent oracle: does an APPROVED dish actually carry something forbidden? Re-derived
    from the attribute table, not from the gate's own verdict."""
    allergies = set(profile.allergies)
    forbidden = set((data.diet_rules().get(profile.diet) or {}).get("forbidden_props", []))
    for ing in recipe.ingredients:
        attrs = resolution.resolve_attrs(ing.item)
        if attrs is None:
            continue
        if allergies & set(attrs.get("allergens", [])):
            return f"{ing.item} carries {sorted(allergies & set(attrs['allergens']))}"
        if forbidden & set(attrs.get("diet_props", [])):
            return f"{ing.item} is {sorted(forbidden & set(attrs['diet_props']))} (not {profile.diet})"
    return None


def run_eval(fixtures_path: str | Path | None = None) -> EvalReport:
    dishes = _load(fixtures_path)
    total = resolved = misresolved = approvals = pairs = unsafe = 0
    unsafe_examples: list = []

    for dish in dishes:
        for c in (resolution.classify(s) for s in dish["ingredients"]):
            total += 1
            resolved += int(c.outcome == "resolved")
            misresolved += int(c.outcome == "misresolved")
        recipe = _to_recipe(dish)
        for prof in EVAL_PROFILES:
            profile = Profile.from_dict(prof)
            pairs += 1
            if gate(recipe, profile).approved:
                approvals += 1
                why = _carries_violation(recipe, profile)
                if why:
                    unsafe += 1
                    unsafe_examples.append(f"{dish['name']} approved for {prof['name']}: {why}")

    return EvalReport(
        dishes=len(dishes), profiles=len(EVAL_PROFILES), ingredient_strings=total,
        resolved=resolved, coverage=round(resolved / total, 3) if total else 0.0,
        misresolved=misresolved, approvals=approvals,
        approval_rate=round(approvals / pairs, 3) if pairs else 0.0,
        unsafe_approvals=unsafe, unsafe_examples=unsafe_examples,
    )


def format_report(r: EvalReport) -> str:
    ok = lambda b: "PASS" if b else "FAIL"
    return "\n".join([
        f"kitchenaid eval — {r.dishes} real dishes × {r.profiles} profiles",
        "-" * 56,
        f"  SAFETY (constraint-satisfaction):",
        f"    mis-resolutions   : {r.misresolved:>4}   [{ok(r.misresolved == 0)}] (must be 0)",
        f"    unsafe approvals  : {r.unsafe_approvals:>4}   [{ok(r.unsafe_approvals == 0)}] (must be 0)",
        f"  COVERAGE:",
        f"    resolved strings  : {r.resolved}/{r.ingredient_strings} = {r.coverage:.1%}   "
        f"[{ok(r.coverage >= COVERAGE_FLOOR)}] (floor {COVERAGE_FLOOR:.0%})",
        f"  USABILITY:",
        f"    approval rate     : {r.approval_rate:.1%} ({r.approvals}/{r.dishes * r.profiles})",
        "-" * 56,
        f"  OVERALL: {ok(r.passes)}",
    ] + ([""] + [f"  ⚠ {e}" for e in r.unsafe_examples] if r.unsafe_examples else []))


if __name__ == "__main__":
    import sys

    report = run_eval()
    print(format_report(report))
    # Exit non-zero on any safety/coverage regression so CI can gate on it.
    sys.exit(0 if report.passes else 1)
