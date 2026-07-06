"""HTTP API (ship) — a thin FastAPI adapter over the Concierge.

No logic lives here: it deserializes a request, hands it to the in-process agent team via the
Concierge, persists learned taste through the Profile Keeper, and serializes the response
(including the handoff trace) to JSON. The whole design earned this — because the agent loop
is plain functions and the gate is deterministic, the HTTP surface is a ~1-file adapter, not
a rewrite.

The request-handling logic is a plain `KitchenaidService` (testable with no HTTP). The
FastAPI wiring is a thin layer, guarded so the module imports even without FastAPI installed.

Run:  uvicorn kitchenaid.api:app --reload      (needs: pip install fastapi uvicorn)
"""

from typing import Optional

from .concierge import AGENT_TEAM, AgentOptions, Concierge, ConciergeResponse
from .models import Profile
from .pantry import Pantry
from .profile_keeper import ProfileKeeper


class KitchenaidService:
    """Stateful front door for HTTP: one Concierge per user (session memory = last meal),
    taste persisted per user via the Profile Keeper."""

    def __init__(self, keeper: Optional[ProfileKeeper] = None) -> None:
        self.keeper = keeper or ProfileKeeper()
        self._sessions: "dict[str, Concierge]" = {}

    def _concierge(self, user_id: str) -> Concierge:
        if user_id not in self._sessions:
            self._sessions[user_id] = Concierge()
        return self._sessions[user_id]

    def chat(self, user_id: str, query: str, profile: dict, pantry: Optional[dict] = None,
             options: Optional[dict] = None) -> dict:
        prof = Profile.from_dict(profile)
        pan = Pantry.from_dict(pantry) if pantry else None
        opts = AgentOptions.from_dict(options)
        taste = self.keeper.load_taste(user_id)                 # Profile Keeper: read
        resp = self._concierge(user_id).handle(query, prof, pan, taste, opts)
        if opts.taster:                                         # respect the learning toggle
            self.keeper.save_taste(user_id, taste)              # Profile Keeper: write
        return _serialize(resp)


# --- serialization (dataclasses -> friendly JSON) ------------------------------------

def _serialize(resp: ConciergeResponse) -> dict:
    rec = resp.recommendation
    return {
        "intent": resp.intent,
        "message": resp.message,
        "agents_used": resp.agents_used,
        "used_llm": resp.used_llm,
        "trace": [{"agent": e.agent, "action": e.action, "detail": e.detail, "ms": e.ms}
                  for e in resp.trace],
        "meal": _meal(rec) if rec is not None and rec.chosen is not None else None,
        "grocery": _grocery(resp.shopping) if resp.shopping is not None else None,
    }


def _meal(rec) -> dict:
    r, g = rec.chosen, rec.chosen_gate
    return {
        "name": r.name, "cuisine": r.cuisine, "time_min": r.time_min, "servings": r.servings,
        "cost_per_serving_usd": g.cost_per_serving_usd,
        "calories_per_serving": g.calories_per_serving,
        "protein_per_serving_g": g.protein_per_serving_g,
        "flags": g.flags,
        "why": rec.why,
        "ingredients": [{"item": i.item, "grams": i.grams} for i in r.ingredients],
    }


def _grocery(plan) -> dict:
    return {
        "total_cost_usd": plan.total_cost_usd,
        "cost_per_serving_usd": plan.cost_per_serving_usd,
        "items": [{"item": i.item, "grams": i.grams, "est_cost_usd": i.est_cost_usd}
                  for i in plan.items],
        "substitutions": [{"original": s.original, "replacement": s.replacement, "reason": s.reason}
                          for s in plan.substitutions],
    }


# --- FastAPI wiring (thin, optional) -------------------------------------------------

def create_app():
    """Build the FastAPI app. Raises ImportError if FastAPI isn't installed."""
    from typing import Optional

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    app = FastAPI(title="kitchenaid", version="0.1.0",
                  description="A daily kitchen agent — Concierge over the whole team.")
    # Open CORS for local dev / a static web client. Production should restrict allow_origins.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])
    service = KitchenaidService()

    class ChatRequest(BaseModel):
        user_id: str
        query: str
        profile: dict
        pantry: Optional[dict] = None   # Optional[] not `dict | None`: pydantic evaluates this on 3.9
        options: Optional[dict] = None  # agent toggles: creative_chef / shopper / taster

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok",
                "agents": ["Concierge", "Chef", "Dietitian", "Shopper", "ProfileKeeper", "Taster"]}

    @app.get("/agents")
    def agents() -> dict:
        """The team, as data: who they are, what they do, and which can be toggled.
        The Dietitian is not toggleable by design — safety is structural."""
        return {"agents": AGENT_TEAM}

    @app.post("/chat")
    def chat(req: ChatRequest) -> dict:
        """Natural-language turn: the Concierge routes to the right agents. Try queries like
        'quick dinner', 'what do I need to buy for dinner', 'that was too spicy', 'plan my week'."""
        return service.chat(req.user_id, req.query, req.profile, req.pantry, req.options)

    return app


try:                          # module-level app for `uvicorn kitchenaid.api:app`
    app = create_app()
except ImportError:           # FastAPI not installed — KitchenaidService still works
    app = None
