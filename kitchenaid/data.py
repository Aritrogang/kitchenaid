"""Deterministic source loaders + lookups.

Each source is a thin local seed today, swappable for a real API behind these functions
without touching the gate:
  - lookup_nutrition()  -> USDA FoodData Central
  - lookup_price()      -> a retailer / price-feed API (weakest source; see Phase 0 design)
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

from .models import Recipe

_DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_json(name: str):
    with open(_DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _strip_comments(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


@functools.lru_cache(maxsize=1)
def nutrition_table() -> dict:
    return _strip_comments(_load_json("nutrition.json"))


@functools.lru_cache(maxsize=1)
def price_table() -> dict:
    return _strip_comments(_load_json("prices.json"))


@functools.lru_cache(maxsize=1)
def allergen_labels() -> dict:
    """Allergen key -> human display label (the allergen vocabulary)."""
    return _strip_comments(_load_json("allergens.json"))


@functools.lru_cache(maxsize=1)
def ingredient_attrs() -> dict:
    """Canonical ingredient -> {allergens: [...], diet_props: [...]}. The gate's authority."""
    return _strip_comments(_load_json("ingredients.json"))


@functools.lru_cache(maxsize=1)
def diet_rules() -> dict:
    return _strip_comments(_load_json("diet_rules.json"))


@functools.lru_cache(maxsize=1)
def recipes() -> list[Recipe]:
    return [Recipe.from_dict(r) for r in _load_json("recipes.json")]


def lookup_nutrition(item: str) -> dict | None:
    """Per-100g macros for an ingredient, or None if unknown. (USDA FDC seam.)"""
    return nutrition_table().get(item.lower())


def lookup_price(item: str) -> float | None:
    """USD per 100g for an ingredient, or None if unknown. (Pricing-feed seam.)"""
    rec = price_table().get(item.lower())
    return rec["usd_per_100g"] if rec else None


def lookup_ingredient(item: str) -> dict | None:
    """Attributes (allergens + diet_props) for an ingredient, or None if unknown."""
    return ingredient_attrs().get(item.lower())
