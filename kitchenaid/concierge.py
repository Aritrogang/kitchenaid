"""The Concierge (Phase 5) — the orchestrator and front door.

Holds the session, interprets intent, decides which specialists to call and in what order,
and assembles the answer. It is also the **cost governor**: a plain "what's for dinner"
routes down a deterministic fast path (Chef + Dietitian, no LLM, no Shopper) — the whole team
only spins up when the turn actually needs it. Every handoff is recorded in a trace so the
routing is observable.

Intent classification is deterministic keyword matching by default (free, reproducible); an
LLM classifier is a future opt-in, the same way corpus reranking is.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from . import agent, chef
from .dietitian import Dietitian
from .models import Moment, Profile, Recipe
from .pantry import Pantry
from .shopper import Shopper, ShoppingPlan
from .taster import Taster
from .taste import TasteMemory


@dataclass
class TraceEvent:
    agent: str
    action: str
    detail: str = ""
    ms: float = 0.0


@dataclass
class AgentOptions:
    """User-facing toggles for the team. The Dietitian is deliberately NOT here: the safety
    gate is structural and cannot be switched off — that absence is the design."""
    creative_chef: bool = False    # LLM-generated dishes shaped by the user's words (paid, gated)
    shopper: bool = True           # grocery list + substitution re-verify loop
    taster: bool = True            # learn from feedback

    @classmethod
    def from_dict(cls, d: dict | None) -> "AgentOptions":
        d = d or {}
        return cls(
            creative_chef=bool(d.get("creative_chef", False)),
            shopper=bool(d.get("shopper", True)),
            taster=bool(d.get("taster", True)),
        )


# Team metadata served at /agents — the UI renders the team from data, not hardcoding.
AGENT_TEAM = [
    {"id": "concierge", "name": "Concierge", "role": "Routes your request and assembles the answer",
     "detail": "Reads intent (meal / shopping / feedback / weekly plan) and calls only the agents the turn needs — a plain dinner never spins up the whole team.",
     "toggleable": False, "always_on_reason": "It is the front door; every turn starts here."},
    {"id": "chef", "name": "Creative Chef", "role": "Proposes dishes",
     "detail": "Ranks the recipe corpus for your profile and moment. With Creative mode on, it invents new dishes from your exact words using a language model — every invention still goes through the Dietitian.",
     "toggleable": True, "toggle_key": "creative_chef", "toggle_label": "Creative mode (AI-generated dishes)",
     "default": False},
    {"id": "dietitian", "name": "Dietitian", "role": "The safety gate",
     "detail": "Deterministically verifies every candidate against your allergies and diet using an ingredient database — never model judgment. Unknown ingredients are refused, not guessed.",
     "toggleable": False, "always_on_reason": "Safety is structural. No configuration can disable the gate."},
    {"id": "shopper", "name": "Shopper", "role": "Builds your grocery list",
     "detail": "Diffs the plan against your pantry, prices what you need, and proposes cheaper swaps — each swap re-verified by the Dietitian before it's applied.",
     "toggleable": True, "toggle_key": "shopper", "toggle_label": "Grocery lists & smart swaps",
     "default": True},
    {"id": "profile_keeper", "name": "Profile Keeper", "role": "Remembers you",
     "detail": "Stores your profile and learned tastes so every session starts where the last one ended.",
     "toggleable": False, "always_on_reason": "Memory underpins the other agents."},
    {"id": "taster", "name": "Taster", "role": "Learns from feedback",
     "detail": "Turns 'loved it / too spicy / took too long' into taste weights that re-rank future suggestions.",
     "toggleable": True, "toggle_key": "taster", "toggle_label": "Learn from my feedback",
     "default": True},
]


@dataclass
class ConciergeResponse:
    intent: str
    message: str
    recommendation: object | None = None      # agent.Recommendation
    shopping: ShoppingPlan | None = None
    trace: list[TraceEvent] = field(default_factory=list)
    agents_used: int = 0
    used_llm: bool = False


_FEEDBACK_CUES = ("too spicy", "too salty", "too long", "took too long", "too much",
                  "loved", "love it", "loved it", "hated", "didn't like", "disliked",
                  "was great", "was bland", "not a fan")
_SHOPPING_CUES = ("grocery", "shopping list", "what do i need", "what to buy", "buy for",
                  "to buy", "ingredients i need")
_PLAN_CUES = ("this week", "the week", "meal plan", "plan my", "plan the", "few days",
              "for the week")
_FRIDGE_CUES = ("use up", "fridge", "expiring", "about to go", "going bad", "leftover")


class Concierge:
    def __init__(self, dietitian: Dietitian | None = None, shopper: Shopper | None = None,
                 taster: Taster | None = None) -> None:
        self.dietitian = dietitian or Dietitian()
        self.shopper = shopper or Shopper(self.dietitian)   # share the verifier agent
        self.taster = taster or Taster()
        self.last_recipe: Recipe | None = None              # session memory
        self._t0 = 0.0
        self.trace: list[TraceEvent] = []

    # --- intent ----------------------------------------------------------------------

    def classify(self, query: str) -> str:
        q = query.lower()
        if any(c in q for c in _FEEDBACK_CUES):
            return "feedback"
        if any(c in q for c in _SHOPPING_CUES):
            return "shopping"
        if any(c in q for c in _PLAN_CUES):
            return "plan_week"
        if any(c in q for c in _FRIDGE_CUES):
            return "use_fridge"
        return "quick_dinner"

    # --- entry point -----------------------------------------------------------------

    def handle(self, query: str, profile: Profile, pantry: Pantry | None = None,
               taste: TasteMemory | None = None,
               options: AgentOptions | None = None) -> ConciergeResponse:
        self._t0 = time.perf_counter()
        self.trace = []
        opts = options or AgentOptions()
        intent = self.classify(query)
        self._log("Concierge", "route", intent + (" · creative" if opts.creative_chef else ""))

        if intent == "feedback":
            return self._feedback(query, intent, taste, opts)
        if intent == "shopping":
            return self._shopping(query, profile, pantry, taste, intent, opts)
        if intent == "plan_week":
            return self._plan_week(query, profile, taste, intent)
        return self._meal(query, profile, taste, intent, opts)   # quick_dinner / use_fridge

    # --- handlers --------------------------------------------------------------------

    def _recommend(self, query, profile, taste, opts):
        """Corpus path by default; with Creative mode on, invent dishes from the user's own
        words (LLM, budget-gated) and pipe every candidate through the same Dietitian gate.

        If the Dietitian blocks EVERY invention (typically unresolved exotic ingredients
        failing closed), the Concierge runs the propose->verify->repropose loop: it hands the
        Dietitian's reasons back to the Chef and regenerates once with those ingredients
        banned. Still nothing safe -> honest fallback to the corpus."""
        used_llm = False
        if opts.creative_chef:
            moment = agent.parse_moment(query, profile)
            generated = chef.generate_recipes(profile, moment, n=6, hint=query)
            if generated:
                used_llm = True
                self._log("Chef", "generate", f"{len(generated)} invented dishes (LLM)")
                review = self.dietitian.review_batch(generated, profile, moment)
                if review.chosen is None and review.rejected:
                    blocked = _blocked_ingredients(review.rejected)
                    self._log("Dietitian", "reject",
                              f"all {review.considered} blocked — returning reasons to Chef")
                    retry_hint = (f"{query}. STRICT: use only very common supermarket "
                                  f"ingredients. Do NOT use any of: {', '.join(sorted(blocked)[:12])}.")
                    regenerated = chef.generate_recipes(profile, moment, n=6, hint=retry_hint)
                    if regenerated:
                        self._log("Chef", "regenerate", f"{len(regenerated)} revised dishes (LLM)")
                        review = self.dietitian.review_batch(regenerated, profile, moment)
                if review.chosen is not None:
                    rec = agent.Recommendation(
                        query=query, moment=moment, chosen=review.chosen,
                        chosen_gate=review.verdict, rejected=review.rejected,
                        considered=review.considered,
                    )
                    return rec, True
                self._log("Chef", "generate", "no safe invention — falling back to corpus")
            else:
                self._log("Chef", "generate", "unavailable — falling back to corpus")
        rec = agent.recommend(query, profile, dietitian=self.dietitian, taste=taste)
        self._log("Chef", "propose", f"{rec.considered} candidates")
        return rec, used_llm

    def _meal(self, query, profile, taste, intent, opts) -> ConciergeResponse:
        rec, used_llm = self._recommend(query, profile, taste, opts)
        self._log("Dietitian", "verify", f"approved {int(bool(rec.chosen))}, blocked {len(rec.rejected)}")
        self.last_recipe = rec.chosen
        return self._respond(intent, self._say_meal(rec), agents=2, used_llm=used_llm,
                             recommendation=rec)

    def _shopping(self, query, profile, pantry, taste, intent, opts) -> ConciergeResponse:
        rec, used_llm = self._recommend(query, profile, taste, opts)
        self._log("Dietitian", "verify", f"approved {int(bool(rec.chosen))}")
        self.last_recipe = rec.chosen
        if not rec.chosen:
            return self._respond(intent, self._say_meal(rec), agents=2, used_llm=used_llm,
                                 recommendation=rec)
        if not opts.shopper:
            self._log("Concierge", "skip", "Shopper disabled by user")
            return self._respond(intent, self._say_meal(rec) +
                                 "\n(Shopper is off — enable it in Agents to get the grocery list.)",
                                 agents=2, used_llm=used_llm, recommendation=rec)
        plan = self.shopper.plan(rec.chosen, pantry or Pantry(), profile)
        self._log("Shopper", "source", f"{len(plan.items)} to buy, ${plan.total_cost_usd:.2f}"
                                       + (f", {len(plan.substitutions)} subs" if plan.substitutions else ""))
        return self._respond(intent, self._say_shopping(rec, plan), agents=3, used_llm=used_llm,
                             recommendation=rec, shopping=plan)

    def _feedback(self, query, intent, taste, opts) -> ConciergeResponse:
        if not opts.taster:
            self._log("Concierge", "skip", "Taster disabled by user")
            return self._respond(intent, "Feedback noted, but learning is switched off — "
                                          "enable the Taster in Agents if you want me to adapt.", agents=0)
        if taste is None or self.last_recipe is None:
            return self._respond(intent, "Noted — but I need a recent meal and a taste profile "
                                          "to learn from. Ask me for a meal first.", agents=0)
        tags = self._parse_feedback(query)
        self.taster.record(self.last_recipe, tags, taste)
        self._log("Taster", "learn", f"{self.last_recipe.name}: {', '.join(tags) or 'no tags'}")
        return self._respond(intent, f"Got it — updated your taste profile from "
                                     f"'{self.last_recipe.name}' ({', '.join(tags) or 'noted'}).", agents=1)

    def _plan_week(self, query, profile, taste, intent, days: int = 5) -> ConciergeResponse:
        candidates = chef.propose(profile, Moment(), taste=taste)
        review_used = 0
        plan: list[Recipe] = []
        seen = set()
        for r in candidates:
            v = self.dietitian.review(r, profile)
            review_used += 1
            if v.approved and r.cuisine not in seen:
                plan.append(r)
                seen.add(r.cuisine)
            if len(plan) >= days:
                break
        self._log("Chef", "propose", f"{len(candidates)} candidates")
        self._log("Dietitian", "verify", f"{review_used} reviewed, {len(plan)} selected")
        self.last_recipe = plan[0] if plan else None
        return self._respond(intent, self._say_plan(plan), agents=2)

    # --- helpers ---------------------------------------------------------------------

    def _parse_feedback(self, query: str) -> list[str]:
        q = query.lower()
        tags = []
        if "too spicy" in q or "too hot" in q:
            tags.append("too spicy")
        if "too long" in q or "took too long" in q or "took forever" in q:
            tags.append("too long")
        if "too much" in q or "made too much" in q:
            tags.append("too much")
        if any(w in q for w in ("loved", "love it", "loved it", "was great", "amazing")):
            tags.append("loved")
        if any(w in q for w in ("hated", "didn't like", "disliked", "not a fan", "was bland")):
            tags.append("disliked")
        return tags

    def _log(self, agent_name: str, action: str, detail: str = "") -> None:
        self.trace.append(TraceEvent(agent_name, action, detail,
                                     round((time.perf_counter() - self._t0) * 1000, 1)))

    def _respond(self, intent, message, agents, used_llm=False, **kw) -> ConciergeResponse:
        return ConciergeResponse(intent=intent, message=message, trace=list(self.trace),
                                 agents_used=agents, used_llm=used_llm, **kw)

    def _say_meal(self, rec) -> str:
        if not rec.chosen:
            return "Nothing in the corpus clears your hard rules for this one."
        g = rec.chosen_gate
        return (f"{rec.chosen.name} — {rec.chosen.time_min} min, "
                f"~${g.cost_per_serving_usd:.2f}/serving, {g.calories_per_serving:.0f} kcal.")

    def _say_shopping(self, rec, plan) -> str:
        lines = [self._say_meal(rec), f"Grocery list (${plan.total_cost_usd:.2f}):"]
        lines += [f"   {gi.grams:.0f}g {gi.item} (${gi.est_cost_usd:.2f})" for gi in plan.items]
        for s in plan.substitutions:
            lines.append(f"   swapped {s.original} to {s.replacement} ({s.reason})")
        return "\n".join(lines)

    def _say_plan(self, plan) -> str:
        if not plan:
            return "Couldn't assemble a safe plan from the corpus."
        return "Week:\n" + "\n".join(f"   {i+1}. {r.name} ({r.cuisine})" for i, r in enumerate(plan))


def _blocked_ingredients(rejected) -> set:
    """The ingredient strings that caused rejections — fed back to the Chef so a regenerate
    can avoid them. Parsed from the Dietitian's hard-violation messages, which quote the
    offending item as 'contains 'X' ...' or ''X' could not be resolved ...'."""
    out = set()
    for _recipe, verdict in rejected:
        for v in verdict.hard_violations:
            m = re.search(r"'([^']+)'", v)
            if m:
                out.add(m.group(1))
    return out


def format_trace(response: ConciergeResponse) -> str:
    """One-line-per-handoff view of what the Concierge did (observability)."""
    head = f"[intent={response.intent} · agents={response.agents_used} · llm={response.used_llm}]"
    rows = [f"   {e.ms:>6.1f}ms  {e.agent:<10} {e.action:<8} {e.detail}" for e in response.trace]
    return head + "\n" + "\n".join(rows)
