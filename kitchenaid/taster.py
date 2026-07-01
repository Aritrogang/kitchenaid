"""The Taster (Phase 4) — closes the feedback loop.

After a meal it captures plain feedback — loved it / liked it / disliked / too spicy / took
too long / made too much — and updates the TasteMemory the Profile Keeper persists. This is
what makes the whole system adaptive rather than static: the Chef's next suggestions shift
because the numbers behind them moved.
"""

from __future__ import annotations

from .models import Recipe
from .taste import TasteMemory

# Recognized feedback tags (free text is normalized: "too spicy" -> "too_spicy").
_LOVE = {"loved", "loved_it", "love", "amazing", "favorite"}
_LIKE = {"liked", "liked_it", "like", "good", "nice"}
_DISLIKE = {"disliked", "hated", "bad", "meh", "not_a_fan"}


def _norm(tag: str) -> str:
    return tag.strip().lower().replace(" ", "_").replace("-", "_")


class Taster:
    def record(self, recipe: Recipe, feedback, memory: TasteMemory) -> TasteMemory:
        """Apply one meal's feedback to the taste memory. `feedback` is a tag or list of tags
        (e.g. "loved" or ["loved", "too spicy"]). Mutates and returns `memory`."""
        tags = [feedback] if isinstance(feedback, str) else list(feedback)
        for raw in tags:
            self._apply(recipe, _norm(raw), memory)
        return memory

    def _apply(self, recipe: Recipe, tag: str, memory: TasteMemory) -> None:
        if tag in _LOVE:
            self._reward(recipe, memory, cuisine=0.6, ingredient=0.25)
            if recipe.name not in memory.loved:
                memory.loved.append(recipe.name)
        elif tag in _LIKE:
            self._reward(recipe, memory, cuisine=0.3, ingredient=0.12)
        elif tag in _DISLIKE:
            self._reward(recipe, memory, cuisine=-0.4, ingredient=-0.2)
            if recipe.name not in memory.disliked:
                memory.disliked.append(recipe.name)
        elif tag == "too_spicy":
            memory.spice_tolerance -= 1.0
        elif tag == "too_long":
            memory.time_pref -= 1.0
        elif tag == "too_much":
            memory.portion_pref -= 0.25
        # unknown tags are ignored (safe no-op)

    @staticmethod
    def _reward(recipe: Recipe, memory: TasteMemory, cuisine: float, ingredient: float) -> None:
        if recipe.cuisine:
            memory.cuisine[recipe.cuisine] = memory.cuisine.get(recipe.cuisine, 0.0) + cuisine
        for ing in recipe.ingredients:
            memory.ingredient[ing.item] = memory.ingredient.get(ing.item, 0.0) + ingredient
