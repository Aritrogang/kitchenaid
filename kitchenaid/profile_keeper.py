"""The Profile Keeper (Phase 4) — the memory agent.

Owns the persistent user model: structured facts (the Profile — allergies, diet, budget…)
plus the learned TasteMemory. Reads and writes through a pluggable store (see store.py) so
taste survives across sessions — JSON files in dev, Postgres in production, same interface.
Structured facts stay authoritative for the gate; taste memory only nudges ranking.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import Profile
from .store import Store, make_store
from .taste import TasteMemory


class ProfileKeeper:
    """Persistence-agnostic memory agent. Backend is chosen by `make_store`: an explicit
    `store_dir` means JSON files there; otherwise DATABASE_URL decides (Postgres) or falls
    back to the default file store. Pass `store=` to inject a backend directly (tests)."""

    def __init__(self, store_dir: "str | Path | None" = None, *,
                 store: "Store | None" = None) -> None:
        self._store = store if store is not None else make_store(store_dir)

    def load_taste(self, user_id: str) -> TasteMemory:
        return self._store.get_taste(user_id)

    def save_taste(self, user_id: str, memory: TasteMemory) -> None:
        self._store.put_taste(user_id, memory)

    def load_profile_by_id(self, user_id: str) -> Optional[Profile]:
        """The stored server-side profile for a user, or None if we've never seen one."""
        return self._store.get_profile(user_id)

    def save_profile(self, user_id: str, profile: Profile) -> None:
        self._store.put_profile(user_id, profile)

    def load_last_recipe(self, user_id: str):
        """The user's last recommended meal, or None — session memory that survives across
        stateless turns so feedback ('too spicy') can attach to it."""
        return self._store.get_last_recipe(user_id)

    def save_last_recipe(self, user_id: str, recipe) -> None:
        self._store.put_last_recipe(user_id, recipe)

    def forget(self, user_id: str) -> None:
        """Erase everything stored for a user (profile + taste + session + account)."""
        self._store.delete(user_id)

    # --- accounts ---
    def create_user(self, user_id: str, username: str, password_hash: str) -> None:
        self._store.create_user(user_id, username, password_hash)

    def get_user(self, username: str):
        return self._store.get_user(username)

    def load_profile(self, path: "str | Path") -> Profile:
        """Load a Profile from a JSON file (used by the CLI)."""
        with open(path, encoding="utf-8") as f:
            return Profile.from_dict(json.load(f))
