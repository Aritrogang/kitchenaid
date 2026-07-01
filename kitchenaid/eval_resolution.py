"""Resolution-miss dataset — treat the gap as data, not a printout.

Every time a chef (real or simulated) emits ingredient strings, we classify each one and
append the misses to an accumulating JSONL dataset, tagged with the dish and the profile in
play. Over many runs this answers an empirical question far more interesting than a test
count: *how often does the model produce something the safety layer can't classify, and is
the gap benign synonyms (cheap to patch) or modifier-inverted ingredients (which need real
structure)?* This file is the seed of the Phase 6 eval.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import data, resolution
from .models import Profile, Recipe
from .tools import gate

DATASET = Path(__file__).resolve().parent.parent / "eval" / "resolution_misses.jsonl"


class LiveInvariantViolation(AssertionError):
    """Raised if the gate ever approves a recipe with an unresolved/misresolved ingredient.
    This is the live-fire version of fail-closed — a hole the synthetic fuzzer can't reach."""


@dataclass
class RecipeAudit:
    recipe: Recipe
    profile: Profile
    classifications: list[resolution.Classification]
    approved: bool
    hard_violations: list[str]


def has_active_hard_rule(profile: Profile) -> bool:
    """A hard rule is active if the user has any allergy or a restricted diet."""
    return bool(profile.allergies) or data.diet_rules().get(profile.diet) is not None


def invariant_violated(approved: bool, classifications: list[resolution.Classification],
                       active_hard_rule: bool) -> bool:
    """Pure live-fire fail-closed check: when a hard rule is active, an APPROVED recipe must
    be fully resolved (no unresolved/misresolved ingredient). If it isn't, fail-closed has a
    hole the synthetic fuzzer couldn't reach. (With no active hard rule there is nothing to
    verify, so an unresolved ingredient may legitimately pass.)"""
    if not (approved and active_hard_rule):
        return False
    return any(c.outcome != "resolved" for c in classifications)


def audit_recipe(recipe: Recipe, profile: Profile) -> RecipeAudit:
    classifications = [resolution.classify(ing.item) for ing in recipe.ingredients]
    verdict = gate(recipe, profile)

    if invariant_violated(verdict.approved, classifications, has_active_hard_rule(profile)):
        not_clean = [(c.raw, c.outcome) for c in classifications if c.outcome != "resolved"]
        raise LiveInvariantViolation(
            f"{recipe.name!r} APPROVED with non-resolved ingredients under an active hard "
            f"rule: {not_clean}"
        )
    return RecipeAudit(recipe, profile, classifications, verdict.approved, verdict.hard_violations)


def log_misses(audit: RecipeAudit, run_id: str, path: Path = DATASET) -> int:
    """Append every non-resolved ingredient string to the dataset. Returns count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with open(path, "a", encoding="utf-8") as f:
        for c in audit.classifications:
            if c.outcome == "resolved":
                continue
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "run": run_id,
                "dish": audit.recipe.name,
                "ingredient": c.raw,
                "outcome": c.outcome,
                "resolved_to": c.canonical,
                "modifier": c.modifier,
                "severity": c.severity,
                "profile": {"allergies": audit.profile.allergies, "diet": audit.profile.diet},
            }) + "\n")
            written += 1
    return written


def summarize(path: Path = DATASET) -> dict:
    """Aggregate the accumulated dataset across all runs."""
    if not path.exists():
        return {"records": 0}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_outcome = Counter(r["outcome"] for r in rows)
    by_modifier = Counter(r["modifier"] for r in rows if r["modifier"])
    top_strings = Counter(r["ingredient"].lower() for r in rows)
    return {
        "records": len(rows),
        "by_outcome": dict(by_outcome),
        "modifier_gaps": dict(by_modifier),
        "distinct_strings": len(top_strings),
        "most_common": top_strings.most_common(50),
        "critical": [r for r in rows if r["severity"] == "critical"],
    }
