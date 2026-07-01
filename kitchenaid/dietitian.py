"""The Dietitian — kitchenaid's verifier agent (Phase 2).

The first real agent boundary, justified purely by the safety boundary. The Creative Chef
PROPOSES candidate dishes; the Dietitian DISPOSES. It is the ONLY component that can approve
a dish, and it decides with deterministic tools (allergens, diet, nutrition, cost) — never
model judgment. The proposer never touches the gate logic; the verifier never generates.

Phase 1 called `tools.gate()` inline inside the agent loop. Phase 2 moves that call behind
this agent *unchanged* — `GateResult` was already the contract, which is why the split is
nearly free. Every verdict is appended to a decision log so the handoff is observable: the
seed of Phase 5 tracing and the production audit trail (every safety decision recorded).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import tools
from .models import GateResult, Moment, Profile, Recipe


@dataclass
class Review:
    """The result of handing a batch of candidates across the boundary to the Dietitian."""
    chosen: Recipe | None
    verdict: GateResult | None
    rejected: list[tuple[Recipe, GateResult]] = field(default_factory=list)
    considered: int = 0


class Dietitian:
    """Deterministic verifier agent. Owns the safety toolbox; the sole approver of a dish."""

    def __init__(self) -> None:
        self.decisions: list[GateResult] = []   # cumulative audit trail of every verdict

    def review(self, recipe: Recipe, profile: Profile, moment: Moment | None = None) -> GateResult:
        """Verify one candidate against every hard rule; also computes flags, macros, cost."""
        verdict = tools.gate(recipe, profile, moment)
        self.decisions.append(verdict)
        return verdict

    def review_batch(self, recipes, profile: Profile, moment: Moment | None = None) -> Review:
        """Verify candidates in order. The chosen dish is the first that clears EVERY hard
        rule; rejected candidates are returned with their reasons for transparency."""
        recipes = list(recipes)
        chosen: Recipe | None = None
        verdict: GateResult | None = None
        rejected: list[tuple[Recipe, GateResult]] = []
        for recipe in recipes:
            v = self.review(recipe, profile, moment)
            if v.approved:
                if chosen is None:
                    chosen, verdict = recipe, v
            else:
                rejected.append((recipe, v))
        return Review(chosen=chosen, verdict=verdict, rejected=rejected, considered=len(recipes))
