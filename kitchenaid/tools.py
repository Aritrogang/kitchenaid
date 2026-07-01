"""THE GATE — deterministic constraint + nutrition + cost checks.

This is the Dietitian's toolbox. Every function here is pure and deterministic: lookups
and rules, never model judgment. In Phase 1 the single agent calls `gate()` inline; in
Phase 2 these exact functions move behind the Dietitian agent. The interface (GateResult)
is already the agent boundary.

Safety invariant (pinned by tests/test_constraints.py):
    gate(...).approved is True  =>  hard_violations == []
An allergen or diet violation is a HARD violation and always blocks approval. Budget,
macro, time, equipment, and skill mismatches are soft FLAGS — informational, never blocking.
"""

from __future__ import annotations

from . import data, resolution
from .models import GateResult, Moment, Profile, Recipe


# --- hard rules: the safety boundary -------------------------------------------------

def check_allergens(recipe: Recipe, profile: Profile) -> list[str]:
    """Return a hard-violation string for every declared allergy this recipe triggers.

    Uses the canonical ingredient-attribute table (structured allergen facts), not substring
    matching — so 'peanut butter' triggers `peanut`, never `milk`. An ingredient not in the
    table cannot be verified, so for an allergic user we fail SAFE and refuse it.
    """
    allergies = set(profile.allergies)
    if not allergies:
        return []
    labels = data.allergen_labels()
    violations: list[str] = []
    for ing in recipe.ingredients:
        res = resolution.resolve(ing.item)
        attrs = data.lookup_ingredient(res.canonical) if res.canonical else None
        if attrs is None:
            violations.append(f"{ing.item!r} could not be resolved to a known ingredient — "
                              f"cannot verify allergens, refusing for safety")
            continue
        for allergen in sorted(allergies & set(attrs.get("allergens", []))):
            violations.append(f"contains {ing.item!r} → {labels.get(allergen, allergen)} allergen")
    return violations


def check_diet(recipe: Recipe, profile: Profile) -> list[str]:
    """Return a hard-violation string if the recipe breaks the user's dietary rule.

    Checks ingredient `diet_props` against the diet's forbidden properties — it does not
    trust the recipe's self-declared diet_tags. The verifier doesn't trust the proposer.
    """
    rule = data.diet_rules().get(profile.diet)
    if not rule:
        return []  # 'none' or an unrecognized diet -> no restriction
    forbidden = set(rule["forbidden_props"])
    violations: list[str] = []
    for ing in recipe.ingredients:
        res = resolution.resolve(ing.item)
        attrs = data.lookup_ingredient(res.canonical) if res.canonical else None
        if attrs is None:
            # Fail CLOSED for diet too: an unverifiable ingredient must block a restricted
            # plan, not slip through. (This is the fail-open bug the review caught.)
            violations.append(f"{ing.item!r} could not be resolved to a known ingredient — "
                              f"cannot verify it is {profile.diet}, refusing for safety")
            continue
        bad = forbidden & set(attrs.get("diet_props", []))
        if bad:
            violations.append(f"contains {ing.item!r} ({'/'.join(sorted(bad))}) → not {profile.diet}")
    return violations


# --- nutrition + cost: deterministic computation -------------------------------------

def compute_nutrition(recipe: Recipe) -> dict:
    """Total + per-serving macros from the nutrition table (per-100g basis)."""
    total = {"kcal": 0.0, "protein_g": 0.0, "carb_g": 0.0, "fat_g": 0.0}
    for ing in recipe.ingredients:
        canonical = resolution.resolve(ing.item).canonical
        macros = data.lookup_nutrition(canonical) if canonical else None
        if not macros:
            continue  # unknown ingredient contributes 0; a real system would flag this
        factor = ing.grams / 100.0
        for k in total:
            total[k] += macros[k] * factor
    servings = max(recipe.servings, 1)
    per = {k: round(v / servings, 1) for k, v in total.items()}
    return {"total": {k: round(v, 1) for k, v in total.items()}, "per_serving": per}


def compute_cost(recipe: Recipe) -> dict:
    """Estimated grocery cost from the price table (per-100g basis). Cost is an ESTIMATE."""
    total = 0.0
    missing: list[str] = []
    for ing in recipe.ingredients:
        canonical = resolution.resolve(ing.item).canonical
        ppg = data.lookup_price(canonical) if canonical else None
        if ppg is None:
            missing.append(ing.item)
            continue
        total += ppg * (ing.grams / 100.0)
    servings = max(recipe.servings, 1)
    return {
        "total_usd": round(total, 2),
        "per_serving_usd": round(total / servings, 2),
        "unpriced_items": missing,
    }


# --- the gate ------------------------------------------------------------------------

def gate(recipe: Recipe, profile: Profile, moment: Moment | None = None) -> GateResult:
    """Run every check and return a single verdict.

    Approval depends ONLY on hard rules (allergens, diet). Everything else is a flag.
    """
    moment = moment or Moment()

    hard: list[str] = []
    hard += check_allergens(recipe, profile)
    hard += check_diet(recipe, profile)

    nutr = compute_nutrition(recipe)
    cost = compute_cost(recipe)
    per = nutr["per_serving"]

    flags: list[str] = []

    # budget (soft)
    if profile.budget_per_meal_usd is not None and cost["per_serving_usd"] > profile.budget_per_meal_usd:
        over = cost["per_serving_usd"] - profile.budget_per_meal_usd
        flags.append(f"${over:.2f}/serving over budget (${cost['per_serving_usd']:.2f} vs ${profile.budget_per_meal_usd:.2f})")

    # calorie target (soft) — flag if >15% over
    if profile.calories_target is not None and per["kcal"] > profile.calories_target * 1.15:
        flags.append(f"{per['kcal']:.0f} kcal/serving over target ({profile.calories_target})")

    # protein floor (soft)
    if profile.protein_target_g is not None and per["protein_g"] < profile.protein_target_g:
        flags.append(f"{per['protein_g']:.0f}g protein/serving under target ({profile.protein_target_g}g)")

    # time (soft) — against the moment if given, else the profile's weeknight norm
    time_budget = (moment.time_available_min if moment.time_available_min is not None
                   else profile.weeknight_minutes)
    if time_budget is not None and recipe.time_min > time_budget:
        flags.append(f"takes {recipe.time_min} min (you have ~{time_budget})")

    # equipment (soft)
    if profile.equipment:
        missing = [e for e in recipe.equipment if e not in profile.equipment]
        if missing:
            flags.append(f"needs equipment you didn't list: {', '.join(missing)}")

    # skill (soft)
    from .models import _SKILL_RANK
    if _SKILL_RANK.get(recipe.skill, 0) > profile.skill_rank:
        flags.append(f"rated {recipe.skill}, above your {profile.skill} level")

    return GateResult(
        recipe_id=recipe.id,
        approved=(len(hard) == 0),
        hard_violations=hard,
        flags=flags,
        calories_per_serving=per["kcal"],
        protein_per_serving_g=per["protein_g"],
        cost_total_usd=cost["total_usd"],
        cost_per_serving_usd=cost["per_serving_usd"],
    )
