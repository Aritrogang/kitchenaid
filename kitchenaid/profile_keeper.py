"""The Profile Keeper (Phase 4) — the memory agent.

Owns the persistent user model: structured facts (the Profile — allergies, diet, budget…)
plus the learned TasteMemory. Reads and writes through a pluggable store (see store.py) so
taste survives across sessions — JSON files in dev, Postgres in production, same interface.
Structured facts stay authoritative for the gate; taste memory only nudges ranking.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Profile
from .store import TasteStore, make_store
from .taste import TasteMemory


class ProfileKeeper:
    """Persistence-agnostic memory agent. Backend is chosen by `make_store`: an explicit
    `store_dir` means JSON files there; otherwise DATABASE_URL decides (Postgres) or falls
    back to the default file store. Pass `store=` to inject a backend directly (tests)."""

    def __init__(self, store_dir: "str | Path | None" = None, *,
                 store: "TasteStore | None" = None) -> None:
        self._store = store if store is not None else make_store(store_dir)

    def load_taste(self, user_id: str) -> TasteMemory:
        return self._store.get_taste(user_id)

    def save_taste(self, user_id: str, memory: TasteMemory) -> None:
        self._store.put_taste(user_id, memory)

    def load_profile(self, path: "str | Path") -> Profile:
        """Load a Profile from a JSON file (used by the CLI). Server-side per-user profile
        persistence rides the same store seam and lands with the auth/multi-user step."""
        with open(path, encoding="utf-8") as f:
            return Profile.from_dict(json.load(f))
