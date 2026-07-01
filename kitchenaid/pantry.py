"""Pantry model (Phase 3) — what the user already has on hand, in grams.

Keys are resolved to canonical ingredients on load (so "chicken" and "chicken breast" merge),
which lets the Shopper diff a recipe against the pantry accurately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import resolution


@dataclass
class Pantry:
    items: dict[str, float] = field(default_factory=dict)   # canonical item -> grams on hand

    def grams(self, item: str) -> float:
        canon = resolution.resolve(item).canonical or item.lower()
        return self.items.get(canon, 0.0)

    @classmethod
    def from_dict(cls, d: dict) -> "Pantry":
        items: dict[str, float] = {}
        for k, v in d.items():
            if k.startswith("_"):
                continue
            canon = resolution.resolve(k).canonical or k.lower()
            items[canon] = items.get(canon, 0.0) + float(v)
        return cls(items=items)

    @classmethod
    def load(cls, path: str | Path) -> "Pantry":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
