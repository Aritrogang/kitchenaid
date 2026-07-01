"""The Shopper — Phase 3.

Reconciles an approved plan against the pantry, builds the grocery list (quantities + cost),
and proposes substitutions for over-budget items — sending EACH swap back through the
Dietitian to re-verify. That re-verification is kitchenaid's first inter-agent dependency:
the Shopper proposes, but the Dietitian still disposes, so a substitution can never introduce
an allergen or diet violation (no salmon->tofu for a soy-allergic user, no butter->almond
"cream" for a nut-allergic one). Unsafe swaps are recorded as rejected, and the Shopper keeps
looking for one that both re-verifies AND actually saves money.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from . import data, resolution
from .dietitian import Dietitian
from .models import Ingredient, Moment, Profile, Recipe

# Candidate swaps (all alternatives are canonical DB items so they can re-verify). Order
# matters: the cheapest option is listed first, which is often the one that also changes the
# allergen profile — exactly the case the Dietitian re-verify must catch.
_SUBSTITUTIONS: dict[str, list[str]] = {
    "butter": ["vegan butter", "olive oil"],
    "cream": ["coconut milk"],
    "heavy cream": ["coconut milk"],
    "cheese": ["vegan cheese"],
    "parmesan cheese": ["nutritional yeast"],
    "salmon": ["tofu", "cod"],
    "cod": ["tofu"],
    "shrimp": ["tofu"],
    "tuna": ["chickpeas"],
    "chicken breast": ["tofu", "chickpeas"],
    "beef": ["lentils", "mushroom"],
    "pork": ["lentils"],
    "peanut butter": ["tahini"],
    "quinoa": ["white rice"],
}


@dataclass
class GroceryItem:
    item: str
    grams: float
    est_cost_usd: float


@dataclass
class Substitution:
    original: str
    replacement: str
    reason: str
    verified: bool


@dataclass
class ShoppingPlan:
    recipe: Recipe                                   # possibly substituted
    items: list[GroceryItem]
    total_cost_usd: float
    cost_per_serving_usd: float
    substitutions: list[Substitution] = field(default_factory=list)
    rejected_substitutions: list[Substitution] = field(default_factory=list)


class Shopper:
    def __init__(self, dietitian: Dietitian | None = None) -> None:
        self.dietitian = dietitian or Dietitian()

    # --- pantry diff + cost ----------------------------------------------------------

    def _to_buy(self, recipe: Recipe, pantry) -> list[tuple[str, float]]:
        """Grams to buy per ingredient after subtracting what's on hand."""
        out = []
        for ing in recipe.ingredients:
            canon = resolution.resolve(ing.item).canonical or ing.item.lower()
            buy = round(max(0.0, ing.grams - pantry.grams(ing.item)), 1)
            if buy > 0:
                out.append((canon, buy))
        return out

    def _cost(self, to_buy: list[tuple[str, float]]) -> tuple[list[GroceryItem], float]:
        items, total = [], 0.0
        for canon, grams in to_buy:
            ppg = data.lookup_price(canon)
            c = round((ppg or 0.0) * grams / 100.0, 2)
            items.append(GroceryItem(canon, grams, c))
            total += c
        return items, round(total, 2)

    def _buy_cost_of(self, canon: str, grams: float, pantry) -> float:
        buy = max(0.0, grams - pantry.grams(canon))
        return (data.lookup_price(canon) or 0.0) * buy / 100.0

    # --- the substitution re-verify loop (depends on the Dietitian) ------------------

    def plan(self, recipe: Recipe, pantry, profile: Profile, moment: Moment | None = None,
             budget_per_serving: float | None = None) -> ShoppingPlan:
        budget = budget_per_serving if budget_per_serving is not None else profile.budget_per_meal_usd
        working = recipe
        applied: list[Substitution] = []
        rejected: list[Substitution] = []

        items, total = self._cost(self._to_buy(working, pantry))
        guard = 0
        while budget is not None and total / max(working.servings, 1) > budget and guard < 12:
            guard += 1
            swap = self._best_verified_swap(working, pantry, profile, moment, rejected)
            if swap is None:
                break                                   # no safe, cheaper swap left
            working, sub = swap
            applied.append(sub)
            items, total = self._cost(self._to_buy(working, pantry))

        return ShoppingPlan(
            recipe=working,
            items=items,
            total_cost_usd=total,
            cost_per_serving_usd=round(total / max(working.servings, 1), 2),
            substitutions=applied,
            rejected_substitutions=rejected,
        )

    def _best_verified_swap(self, recipe, pantry, profile, moment, rejected):
        """Try to swap the costliest ingredient for a cheaper alternative that the Dietitian
        re-approves. Returns (new_recipe, Substitution) or None. Records unsafe/unhelpful
        candidates in `rejected`."""
        ranked = sorted(
            recipe.ingredients,
            key=lambda ing: -self._buy_cost_of(resolution.resolve(ing.item).canonical or ing.item.lower(),
                                                ing.grams, pantry),
        )
        for ing in ranked:
            canon = resolution.resolve(ing.item).canonical or ing.item.lower()
            old_cost = self._buy_cost_of(canon, ing.grams, pantry)
            for alt in _SUBSTITUTIONS.get(canon, []):
                candidate = _swap(recipe, ing, alt)
                verdict = self.dietitian.review(candidate, profile, moment)   # RE-VERIFY
                if not verdict.approved:
                    rejected.append(Substitution(canon, alt, verdict.hard_violations[0] if verdict.hard_violations else "rejected", False))
                    continue
                alt_canon = resolution.resolve(alt).canonical or alt
                if self._buy_cost_of(alt_canon, ing.grams, pantry) < old_cost:
                    return candidate, Substitution(canon, alt_canon, "cheaper, re-verified safe", True)
                rejected.append(Substitution(canon, alt, "safe but not cheaper", False))
        return None


def _swap(recipe: Recipe, target: Ingredient, new_item: str) -> Recipe:
    new_ings = [Ingredient(new_item, i.grams) if i is target else i for i in recipe.ingredients]
    return replace(recipe, id=f"{recipe.id}+sub", ingredients=new_ings)
