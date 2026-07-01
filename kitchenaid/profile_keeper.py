"""The Profile Keeper (Phase 4) — the memory agent.

Owns the persistent user model: structured facts (the Profile — allergies, diet, budget…)
plus the learned TasteMemory. Reads and writes the store so taste survives across sessions.
Structured facts stay authoritative for the gate; taste memory only nudges ranking.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Profile
from .taste import TasteMemory

_DEFAULT_STORE = Path(__file__).resolve().parent.parent / "state"


class ProfileKeeper:
    def __init__(self, store_dir: str | Path | None = None) -> None:
        self.store = Path(store_dir) if store_dir else _DEFAULT_STORE

    def _taste_path(self, user_id: str) -> Path:
        return self.store / f"{user_id}.taste.json"

    def load_taste(self, user_id: str) -> TasteMemory:
        return TasteMemory.load(self._taste_path(user_id))

    def save_taste(self, user_id: str, memory: TasteMemory) -> None:
        memory.save(self._taste_path(user_id))

    def load_profile(self, path: str | Path) -> Profile:
        with open(path, encoding="utf-8") as f:
            return Profile.from_dict(json.load(f))
