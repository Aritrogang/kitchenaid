"""The Concierge loop (Phase 2).

Loop:  profile + moment  ->  Creative Chef PROPOSES (ranked)  ->  hand off to the Dietitian,
       which VERIFIES each candidate and returns the first APPROVED meal  ->  assemble the
       answer (with the Dietitian's rejection reasons for transparency).

Phase 1 gated inline; Phase 2 moved that behind the `Dietitian` agent (see dietitian.py).
This loop no longer knows the gate logic — it just asks the Chef to propose and the Dietitian
to dispose. That's the propose->verify trust boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import chef, data
from .dietitian import Dietitian
from .models import GateResult, Moment, Profile, Recipe

# One shared verifier agent; its .decisions log accumulates the audit trail across turns.
_DIETITIAN = Dietitian()

# Aliases map everyday words to canonical ingredient keys used in the data tables.
_ALIASES = {
    "chicken": "chicken breast",
    "rice": "white rice",
    "peanut": "peanut butter",
    "peanuts": "peanut butter",
    "beans": "black beans",
    "pepper": "bell pepper",
    "peppers": "bell pepper",
    "scallions": "scallion",
    "green onion": "scallion",
    "green onions": "scallion",
    "noodle": "noodles",
    "lentil": "lentils",
    "eggs": "egg",
    "carrots": "carrot",
    "onions": "onion",
    "tomatoes": "tomato",
}

_EXPIRING_CUES = ("expir", "use up", "about to go", "going bad", "go bad", "dies",
                  "die tomorrow", "fridge", "leftover", "wilting")
_QUICK_CUES = ("quick", "fast", "in a hurry", "no time")


def parse_moment(query: str, profile: Profile) -> Moment:
    """Best-effort extraction of this meal's constraints from free text.

    Deliberately naive (keyword/regex). Real intent routing is the Concierge's job (Phase 5).
    """
    q = query.lower()
    moment = Moment(servings=2)

    # on-hand ingredients: scan known ingredient keys + aliases
    keys = list(data.nutrition_table().keys())
    found: set[str] = set()
    for key in keys:
        if _mentions(q, key):
            found.add(key)
    for word, canon in _ALIASES.items():
        if _mentions(q, word):
            found.add(canon)
    moment.on_hand = sorted(found)

    # meal type
    for mt in ("breakfast", "lunch", "dinner", "snack"):
        if mt in q:
            moment.meal_type = mt
            break

    # time available
    m = re.search(r"(\d+)\s*(?:min|minute|minutes|m)\b", q)
    if m:
        moment.time_available_min = int(m.group(1))
    elif any(c in q for c in _QUICK_CUES):
        moment.time_available_min = 20

    # servings ("for 4")
    s = re.search(r"\bfor\s+(\d+)\b", q)
    if s:
        moment.servings = int(s.group(1))

    # expiring: if the user signals urgency about the fridge, treat on-hand as expiring
    if any(cue in q for cue in _EXPIRING_CUES):
        moment.expiring = list(moment.on_hand)

    return moment


def _mentions(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


@dataclass
class Recommendation:
    query: str
    moment: Moment
    chosen: Recipe | None = None
    chosen_gate: GateResult | None = None
    rejected: list[tuple[Recipe, GateResult]] = field(default_factory=list)
    considered: int = 0

    @property
    def why(self) -> list[str]:
        """Human-readable reasons the chosen meal fits."""
        if not self.chosen or not self.chosen_gate:
            return []
        g, r, m = self.chosen_gate, self.chosen, self.moment
        used = sorted({i.item for i in r.ingredients} & set(m.on_hand))
        expiring_used = sorted({i.item for i in r.ingredients} & set(m.expiring))
        reasons = []
        if expiring_used:
            reasons.append(f"uses up {', '.join(expiring_used)} before it goes bad")
        elif used:
            reasons.append(f"uses what you have: {', '.join(used)}")
        reasons.append(f"{r.time_min} min, serves {r.servings}")
        reasons.append(f"~${g.cost_per_serving_usd:.2f}/serving (est.), "
                       f"{g.calories_per_serving:.0f} kcal, {g.protein_per_serving_g:.0f}g protein")
        return reasons


def recommend(query: str, profile: Profile, moment: Moment | None = None,
              dietitian: Dietitian | None = None, taste=None) -> Recommendation:
    dietitian = dietitian or _DIETITIAN
    moment = moment or parse_moment(query, profile)

    candidates = chef.propose(profile, moment, taste=taste)        # Chef proposes (taste-aware)
    review = dietitian.review_batch(candidates, profile, moment)   # Dietitian disposes

    return Recommendation(
        query=query,
        moment=moment,
        chosen=review.chosen,
        chosen_gate=review.verdict,
        rejected=review.rejected,
        considered=review.considered,
    )
