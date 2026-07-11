"""The Creative Chef — proposes ranked candidate dishes for the moment.

It PROPOSES; it never gets the final say. The agent runs every candidate it returns through
the deterministic gate (tools.gate). Two backends:

  - deterministic ranker (default, zero dependencies) — ranks the corpus by fit to the
    profile + moment.
  - Claude (optional, when ANTHROPIC_API_KEY is set and `anthropic` is installed) — ranks /
    combines with higher creativity. Falls back to the ranker on any error.

In both cases the chef only ever returns Recipe objects from the corpus, so the gate's
guarantees hold regardless of backend. Free-form invention (constrained, then gated) is a
Phase 3+ extension.
"""

from __future__ import annotations

import json
import os
import sys

from . import budget, config, data
from .models import Ingredient, Moment, Profile, Recipe

MODEL = config.MODELS["rerank"]
# Cheap model for high-volume recipe generation — keep the live miss-dataset run inexpensive.
GEN_MODEL = config.MODELS["generate"]


def propose(profile: Profile, moment: Moment, corpus: list[Recipe] | None = None,
            taste=None) -> list[Recipe]:
    """Rank the corpus for this profile/moment/taste.

    Default is the deterministic, taste-aware ranker — free, reproducible, and it respects
    learned taste. LLM reranking is opt-in via KITCHENAID_LLM_RERANK=1 (a plain "what's for
    dinner" shouldn't spend money — that's the Concierge cost-governor principle), and even
    then learned taste is re-applied on top so Phase 4 is never bypassed.
    """
    corpus = corpus if corpus is not None else data.recipes()
    if os.environ.get("KITCHENAID_LLM_RERANK") and os.environ.get("ANTHROPIC_API_KEY"):
        ranked = _propose_with_claude(profile, moment, corpus)
        if ranked:
            return sorted(ranked, key=lambda r: -taste.score(r)) if taste is not None else ranked
    return _rank(profile, moment, corpus, taste)


# --- generative path: invent free-text recipes (the gate's real adversary) -----------

def generate_recipes(profile: Profile, moment: Moment, n: int = 8,
                     model: str | None = None, hint: str | None = None) -> list[Recipe] | None:
    """Ask Claude to INVENT n recipes as structured data with free-text ingredient strings.

    This is the path that produces ingredient strings the resolver didn't anticipate — the
    whole point of turning the chef loose. Returns None if there's no key / SDK, so callers
    fall back to a simulated set or the corpus. Ingredient `item` strings are intentionally
    left as raw free text; resolution happens downstream in the gate.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None

    diet_line = f" The user's diet is {profile.diet}." if profile.diet != "none" else ""
    allergy_line = f" Avoid these allergens: {', '.join(profile.allergies)}." if profile.allergies else ""
    # The user's own words shape generation — this is the "solution catering to my needs"
    # path. The Dietitian still verifies every result; the hint only steers creativity.
    hint_line = f" The user asked for: \"{hint.strip()}\". Honor that request closely." if hint and hint.strip() else ""
    prompt = (
        f"Invent {n} realistic {moment.meal_type} recipes.{diet_line}{allergy_line}{hint_line} "
        "Write ingredient names the way a home cook would (natural language, brands, "
        "modifiers like 'vegan', 'low-sodium', 'fresh' are fine). "
        "Reply with ONLY a JSON array; each item: "
        '{"name": str, "cuisine": str, "time_min": int, "servings": int, '
        '"ingredients": [{"item": str, "grams": number}]}.'
    )
    # Scale the output budget with n — a fixed cap truncates larger batches, and truncated
    # JSON fails to parse (and still costs tokens). ~300 tok/recipe + overhead, capped.
    used_model, max_tokens = model or GEN_MODEL, min(600 + n * 300, 8000)

    # SPEND GATE: reserve against an upper-bound estimate BEFORE spending. Blocked -> don't
    # call the API. Surfaced to stderr always (a silent budget block would look like a key
    # problem). See kitchenaid/budget.py.
    est_in = max(len(prompt) // 4, 200)
    reservation = budget.LIMITER.reserve(budget.estimate_cost(used_model, est_in, max_tokens),
                                         user=profile.user_id)
    if not reservation.ok:
        print(f"[budget] generation blocked — {reservation.reason}", file=sys.stderr)
        return None

    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=used_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        budget.LIMITER.record(used_model, msg.usage.input_tokens, msg.usage.output_tokens,
                              user=profile.user_id)
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        start, end = text.find("["), text.rfind("]")
        raw = json.loads(text[start:end + 1])
        return [_recipe_from_generated(d, i) for i, d in enumerate(raw)]
    except Exception as e:
        # Silent fallback keeps the keyless path clean, but on a real live run a silent
        # fallback is maddening — set KITCHENAID_DEBUG=1 to see auth/parse/model errors.
        if config.debug():
            print(f"[chef] live generation failed ({type(e).__name__}): {e}", file=sys.stderr)
        return None


def _recipe_from_generated(d: dict, idx: int) -> Recipe:
    return Recipe(
        id=f"gen-{idx}",
        name=d.get("name", f"Generated {idx}"),
        cuisine=d.get("cuisine", ""),
        time_min=int(d.get("time_min", 30)),
        servings=int(d.get("servings", 2)),
        skill="beginner",
        equipment=[],
        diet_tags=[],
        spice_level=0,
        ingredients=[Ingredient(str(i["item"]), float(i.get("grams", 50)))
                     for i in d.get("ingredients", [])],
    )


# --- deterministic ranker ------------------------------------------------------------

def _rank(profile: Profile, moment: Moment, corpus: list[Recipe], taste=None) -> list[Recipe]:
    scored = sorted(corpus, key=lambda r: -_score(r, profile, moment, taste))
    return scored


def _score(recipe: Recipe, profile: Profile, moment: Moment, taste=None) -> float:
    items = {ing.item.lower() for ing in recipe.ingredients}
    score = 0.0

    # use up what's expiring (highest weight), then what's on hand
    score += 3.0 * len({x.lower() for x in moment.expiring} & items)
    score += 2.0 * len({x.lower() for x in moment.on_hand} & items)

    # taste memory (seed): reward liked dish names, punish disliked
    if recipe.name in profile.liked_dishes:
        score += 2.0
    if recipe.name in profile.disliked_dishes:
        score -= 3.0

    # disliked ingredients
    for d in profile.dislikes:
        if any(d in it for it in items):
            score -= 2.0

    # fits the time budget
    time_budget = moment.time_available_min if moment.time_available_min is not None else profile.weeknight_minutes
    if time_budget is not None and recipe.time_min <= time_budget:
        score += 1.0

    # at or below skill
    if recipe.skill == profile.skill or profile.skill_rank >= _rank_skill(recipe.skill):
        score += 0.5

    # learned taste (Phase 4) — feedback-driven weights re-rank future suggestions
    if taste is not None:
        score += taste.score(recipe)

    return score


def _rank_skill(skill: str) -> int:
    return {"beginner": 0, "intermediate": 1, "advanced": 2}.get(skill, 0)


# --- optional Claude backend ---------------------------------------------------------

def _propose_with_claude(profile: Profile, moment: Moment, corpus: list[Recipe]) -> list[Recipe] | None:
    try:
        import anthropic
    except ImportError:
        return None

    by_id = {r.id: r for r in corpus}
    menu = [
        {
            "id": r.id,
            "name": r.name,
            "cuisine": r.cuisine,
            "time_min": r.time_min,
            "diet_tags": r.diet_tags,
            "spice_level": r.spice_level,
            "key_ingredients": [i.item for i in r.ingredients[:5]],
        }
        for r in corpus
    ]
    user_ctx = {
        "diet": profile.diet,
        "allergies": profile.allergies,
        "dislikes": profile.dislikes,
        "skill": profile.skill,
        "liked_dishes": profile.liked_dishes,
        "moment": {
            "meal_type": moment.meal_type,
            "time_available_min": moment.time_available_min,
            "on_hand": moment.on_hand,
            "expiring": moment.expiring,
        },
    }
    prompt = (
        "You are the Creative Chef in a meal-planning system. Rank the menu below for this "
        "user and moment, best first. A separate Dietitian will deterministically verify hard "
        "rules (allergies, diet), so optimize for fit, what's on hand, and what's expiring.\n\n"
        f"USER + MOMENT:\n{json.dumps(user_ctx)}\n\n"
        f"MENU:\n{json.dumps(menu)}\n\n"
        'Reply with ONLY a JSON array of recipe ids, best first, e.g. ["id1","id2"].'
    )
    # SPEND GATE before this paid rerank call — blocked falls back to the deterministic ranker.
    est_in = max(len(prompt) // 4, 200)
    if not budget.LIMITER.reserve(budget.estimate_cost(MODEL, est_in, 400),
                                  user=profile.user_id).ok:
        return None
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        budget.LIMITER.record(MODEL, msg.usage.input_tokens, msg.usage.output_tokens,
                              user=profile.user_id)
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        start, end = text.find("["), text.rfind("]")
        ids = json.loads(text[start : end + 1]) if start != -1 else []
        ordered = [by_id[i] for i in ids if i in by_id]
        # append any the model omitted, in deterministic-rank order, so the gate sees all
        seen = {r.id for r in ordered}
        ordered += [r for r in _rank(profile, moment, corpus) if r.id not in seen]
        return ordered or None
    except Exception:
        return None  # any API/parse failure -> deterministic ranker
