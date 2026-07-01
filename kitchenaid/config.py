"""Single source of truth for kitchenaid's AI/API surface.

The deterministic core — the gate (allergens, diet, nutrition, cost) — needs NO API and must
never depend on a model. Only *generation* talks to an LLM. Centralizing the model choices
and env vars here keeps the cost story legible and gives the future Concierge (Phase 5) one
place to route from.

Env vars (all optional; the core loop runs with none of them):
  ANTHROPIC_API_KEY        enable the live Creative Chef (text generation)
  ANTHROPIC_GEN_MODEL      override the high-volume generation model (default: Haiku, cheap)
  ANTHROPIC_MODEL          override the corpus-rerank model (default: Sonnet)
  ANTHROPIC_REASON_MODEL   override the deep-reasoning model (future Concierge; default: Opus)
  KITCHENAID_DEBUG=1       surface live-call errors instead of silently falling back
  VOYAGE_API_KEY           (Phase 4) embeddings for taste memory — NOT used today
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a gitignored .env at the project root into the environment,
    without overriding anything already set. Zero-dependency, so the key can live in a file
    (never pasted into chat or committed) and every entry point picks it up."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()  # must run BEFORE MODELS reads the environment below

# Model registry by ROLE, not by call site — so routing/cost decisions live in one place.
MODELS = {
    "generate": os.environ.get("ANTHROPIC_GEN_MODEL", "claude-haiku-4-5-20251001"),  # high-volume, cheap
    "rerank":   os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),              # balanced
    "reason":   os.environ.get("ANTHROPIC_REASON_MODEL", "claude-opus-4-8"),         # deep (future Concierge)
}

# Spend guardrail — conservative by default so a runaway loop can't destroy your credits.
# You opt INTO spending more; the defaults protect you. See kitchenaid/budget.py.
LIMITS = {
    "max_calls_per_run": int(os.environ.get("KITCHENAID_MAX_CALLS_PER_RUN", "25")),
    "max_calls_per_day": int(os.environ.get("KITCHENAID_MAX_CALLS_PER_DAY", "200")),
    "max_usd_per_day":   float(os.environ.get("KITCHENAID_MAX_USD_PER_DAY", "1.00")),
    "spend_ledger":      os.environ.get("KITCHENAID_SPEND_LEDGER", "eval/spend_ledger.jsonl"),
}


def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def sdk_installed() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def debug() -> bool:
    return bool(os.environ.get("KITCHENAID_DEBUG"))


def ai_status() -> dict:
    """Preflight snapshot — what's wired and what's missing for the live path."""
    missing = []
    if not has_api_key():
        missing.append("ANTHROPIC_API_KEY not set")
    if not sdk_installed():
        missing.append("`pip install anthropic`")
    return {
        "api_key_present": has_api_key(),
        "anthropic_sdk_installed": sdk_installed(),
        "models": dict(MODELS),
        "live_generation_ready": has_api_key() and sdk_installed(),
        "missing": missing,
    }
