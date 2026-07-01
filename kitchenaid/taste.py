"""Taste memory (Phase 4) — the learned half of "adapts to the person".

A deterministic, feature-based model of what a user likes: weights over cuisines and
ingredients, plus scalar preferences for spice and time. It produces a `score(recipe)` the
Chef's ranker adds in, so feedback measurably changes future suggestions. This is the seed;
real semantic embeddings of rated dishes are a clean swap behind the same `score()` interface
(the taste analogue of nutrition=seed / USDA-FDC=swap).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import Recipe


@dataclass
class TasteMemory:
    cuisine: dict[str, float] = field(default_factory=dict)      # cuisine -> learned weight
    ingredient: dict[str, float] = field(default_factory=dict)   # canonical ingredient -> weight
    spice_tolerance: float = 0.0    # < 0 after "too spicy" -> penalizes spicy dishes
    time_pref: float = 0.0          # < 0 after "took too long" -> penalizes slow dishes
    portion_pref: float = 0.0       # < 0 after "made too much"
    loved: list[str] = field(default_factory=list)      # kept for interpretability
    disliked: list[str] = field(default_factory=list)

    def score(self, recipe: Recipe) -> float:
        """Higher = better fit to learned taste. Added into the Chef's ranking."""
        s = self.cuisine.get(recipe.cuisine, 0.0)
        if recipe.ingredients:
            s += 3.0 * sum(self.ingredient.get(i.item, 0.0) for i in recipe.ingredients) / len(recipe.ingredients)
        s += self.spice_tolerance * recipe.spice_level * 0.5     # spicy dishes suffer if tolerance < 0
        s += self.time_pref * (recipe.time_min / 30.0)           # slow dishes suffer if time_pref < 0
        return round(s, 3)

    # --- persistence (the Profile Keeper's store) ------------------------------------

    def to_dict(self) -> dict:
        return {
            "cuisine": self.cuisine, "ingredient": self.ingredient,
            "spice_tolerance": self.spice_tolerance, "time_pref": self.time_pref,
            "portion_pref": self.portion_pref, "loved": self.loved, "disliked": self.disliked,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TasteMemory":
        return cls(
            cuisine=dict(d.get("cuisine", {})),
            ingredient=dict(d.get("ingredient", {})),
            spice_tolerance=float(d.get("spice_tolerance", 0.0)),
            time_pref=float(d.get("time_pref", 0.0)),
            portion_pref=float(d.get("portion_pref", 0.0)),
            loved=list(d.get("loved", [])),
            disliked=list(d.get("disliked", [])),
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "TasteMemory":
        p = Path(path)
        if not p.exists():
            return cls()
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
