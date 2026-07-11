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

import os
import uuid
from typing import Optional

from . import accounts, auth
from .concierge import AGENT_TEAM, AgentOptions, Concierge, ConciergeResponse
from .models import Profile
from .pantry import Pantry
from .profile_keeper import ProfileKeeper


class ProfileRequired(Exception):
    """A chat turn arrived with no profile and none is stored for this user."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            f"No profile provided and none stored for user '{user_id}'. Send a profile in the "
            f"request, or PUT /profile/{user_id} once and omit it thereafter."
        )


class KitchenaidService:
    """Stateful front door for HTTP: one Concierge per user (session memory = last meal),
    with the profile and learned taste persisted per user via the Profile Keeper."""

    def __init__(self, keeper: Optional[ProfileKeeper] = None) -> None:
        self.keeper = keeper or ProfileKeeper()
        self._sessions: "dict[str, Concierge]" = {}

    def _concierge(self, user_id: str) -> Concierge:
        if user_id not in self._sessions:
            self._sessions[user_id] = Concierge()
        return self._sessions[user_id]

    def _resolve_profile(self, user_id: str, profile: Optional[dict]) -> Profile:
        """A request may carry the profile (we persist it) or omit it (we load the stored one).
        The gate always runs on a concrete Profile — never a partial or a guess."""
        if profile is not None:
            prof = Profile.from_dict(profile)
            self.keeper.save_profile(user_id, prof)             # server remembers the latest
            return prof
        stored = self.keeper.load_profile_by_id(user_id)
        if stored is None:
            raise ProfileRequired(user_id)
        return stored

    def chat(self, user_id: str, query: str, profile: Optional[dict] = None,
             pantry: Optional[dict] = None, options: Optional[dict] = None) -> dict:
        prof = self._resolve_profile(user_id, profile)
        pan = Pantry.from_dict(pantry) if pantry else None
        opts = AgentOptions.from_dict(options)
        taste = self.keeper.load_taste(user_id)                 # Profile Keeper: read
        resp = self._concierge(user_id).handle(query, prof, pan, taste, opts)
        if opts.taster:                                         # respect the learning toggle
            self.keeper.save_taste(user_id, taste)              # Profile Keeper: write
        return _serialize(resp)

    def get_profile(self, user_id: str) -> Optional[dict]:
        prof = self.keeper.load_profile_by_id(user_id)
        return prof.to_dict() if prof is not None else None

    def put_profile(self, user_id: str, profile: dict) -> dict:
        # The path's user_id is authoritative; the body need not repeat it.
        prof = Profile.from_dict({**profile, "user_id": user_id})
        self.keeper.save_profile(user_id, prof)
        return prof.to_dict()

    def forget(self, user_id: str) -> dict:
        """Erase a user's stored profile + taste + account and drop their in-memory session."""
        self.keeper.forget(user_id)
        self._sessions.pop(user_id, None)
        return {"deleted": True, "user_id": user_id}

    def register(self, username: str, password: str) -> dict:
        """Create an account and return a token. Raises DuplicateUser / ValueError."""
        accounts.validate_username(username)
        accounts.validate_password(password)
        user_id = uuid.uuid4().hex
        self.keeper.create_user(user_id, username, accounts.hash_password(password))
        return {"user_id": user_id, "username": username, "token": auth.create_token(user_id)}

    def login(self, username: str, password: str) -> dict:
        """Verify credentials and return a token. Raises BadCredentials (same for unknown user
        or wrong password, so the response can't be used to enumerate usernames)."""
        rec = self.keeper.get_user(username)
        if rec is None or not accounts.verify_password(password, rec["password_hash"]):
            raise accounts.BadCredentials()
        return {"user_id": rec["user_id"], "username": username,
                "token": auth.create_token(rec["user_id"])}


# A safety/medical disclaimer returned with every answer. An app that makes allergen claims
# must never imply certainty: the gate checks the profile, but labels and formulations change.
# This is product copy, NOT a substitute for the legal review tracked in docs/LEGAL.md.
DISCLAIMER = (
    "kitchenaid checks each dish against the allergies and diet in your profile, but it can't "
    "guarantee safety: ingredient labels and recipes change, and cross-contamination happens. "
    "Always read the packaging yourself, and consult a medical professional for medical dietary "
    "needs or a diagnosed allergy."
)


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
        "disclaimer": DISCLAIMER,
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

    from fastapi import Body, Depends, FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    app = FastAPI(title="kitchenaid", version="0.1.0",
                  description="A daily kitchen agent — Concierge over the whole team.")
    # CORS origins from env: "*" (dev default) or a comma-separated allowlist in production.
    _cors = os.environ.get("KITCHENAID_CORS_ORIGINS", "*").strip()
    origins = ["*"] if _cors == "*" else [o.strip() for o in _cors.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"],
                       allow_headers=["*"])
    service = KitchenaidService()

    def _identity(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
        """The authenticated user when auth is on (KITCHENAID_AUTH_SECRET set), else None.
        When on, identity comes from a verified Bearer token — never client-supplied input."""
        if not auth.enabled():
            return None
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        try:
            return auth.user_from_token(authorization.split(" ", 1)[1].strip())
        except auth.AuthError as e:
            raise HTTPException(status_code=401, detail=str(e))

    def _authorize(identity: Optional[str], user_id: str) -> None:
        """With auth on, you may only touch your own data."""
        if identity is not None and identity != user_id:
            raise HTTPException(status_code=403, detail="token identity does not match that user")

    class ChatRequest(BaseModel):
        # Optional: with auth on, identity comes from the token and this is ignored; with auth
        # off, it names the user. Optional[] not `str | None` — pydantic evaluates this on 3.9.
        user_id: Optional[str] = None
        query: str
        # Optional: send it to set/update the stored profile, or omit it and the server uses
        # the one it already has.
        profile: Optional[dict] = None
        pantry: Optional[dict] = None
        options: Optional[dict] = None  # agent toggles: creative_chef / shopper / taster

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "auth": auth.enabled(),
                "agents": ["Concierge", "Chef", "Dietitian", "Shopper", "ProfileKeeper", "Taster"]}

    @app.get("/agents")
    def agents() -> dict:
        """The team, as data: who they are, what they do, and which can be toggled.
        The Dietitian is not toggleable by design — safety is structural."""
        return {"agents": AGENT_TEAM}

    class Credentials(BaseModel):
        username: str
        password: str

    def _require_auth_configured() -> None:
        if not auth.enabled():
            raise HTTPException(status_code=503,
                                detail="accounts are unavailable: set KITCHENAID_AUTH_SECRET")

    @app.post("/auth/register", status_code=201)
    def register(creds: Credentials) -> dict:
        """Create an account (username + password) and return a bearer token. Then PUT your
        profile and chat with `Authorization: Bearer <token>` — your data is yours alone."""
        _require_auth_configured()
        try:
            return service.register(creds.username, creds.password)
        except accounts.DuplicateUser:
            raise HTTPException(status_code=409, detail="username already taken")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    @app.post("/auth/login")
    def login(creds: Credentials) -> dict:
        """Exchange username + password for a fresh bearer token."""
        _require_auth_configured()
        try:
            return service.login(creds.username, creds.password)
        except accounts.BadCredentials:
            raise HTTPException(status_code=401, detail="invalid username or password")

    @app.post("/chat")
    def chat(req: ChatRequest, identity: Optional[str] = Depends(_identity)) -> dict:
        """Natural-language turn: the Concierge routes to the right agents. Try queries like
        'quick dinner', 'what do I need to buy for dinner', 'that was too spicy', 'plan my week'.
        Omit `profile` to reuse the stored one (400 if none was ever set). With auth on, the
        user is the token subject; the body's user_id is ignored."""
        uid = identity if identity is not None else req.user_id
        if uid is None:
            raise HTTPException(status_code=400,
                                detail="user_id is required (or send a Bearer token when auth is on)")
        try:
            return service.chat(uid, req.query, req.profile, req.pantry, req.options)
        except ProfileRequired as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/profile/{user_id}")
    def get_profile(user_id: str, identity: Optional[str] = Depends(_identity)) -> dict:
        """The stored profile for a user (404 if none set yet)."""
        _authorize(identity, user_id)
        prof = service.get_profile(user_id)
        if prof is None:
            raise HTTPException(status_code=404, detail=f"No stored profile for user '{user_id}'.")
        return prof

    @app.put("/profile/{user_id}")
    def put_profile(user_id: str, profile: dict = Body(...),
                    identity: Optional[str] = Depends(_identity)) -> dict:
        """Create or replace a user's profile. The path's user_id is authoritative."""
        _authorize(identity, user_id)
        return service.put_profile(user_id, profile)

    @app.delete("/profile/{user_id}")
    def delete_profile(user_id: str, identity: Optional[str] = Depends(_identity)) -> dict:
        """Erase everything stored for a user — profile and learned taste (right to erasure)."""
        _authorize(identity, user_id)
        return service.forget(user_id)

    return app


try:                          # module-level app for `uvicorn kitchenaid.api:app`
    app = create_app()
except ImportError:           # FastAPI not installed — KitchenaidService still works
    app = None
