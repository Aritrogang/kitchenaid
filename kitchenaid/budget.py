"""Spend guardrail — a deterministic budget gate in front of every paid LLM call.

Same philosophy as the allergen gate: a hard limit enforced BEFORE the irreversible action
(here, spending credits), failing CLOSED. The deterministic / keyless paths never touch this
— it gates only real API calls. This is the primitive the Phase 5 Concierge cost-governor
grows from.

Two-part enforcement so a single call can't overshoot:
  * reserve(estimated_usd) is checked BEFORE the call (per-run calls, per-day calls, and
    today's spend + this call's estimate vs the daily cap).
  * record(model, usage) writes ACTUAL usage to a persistent ledger AFTER the call, so
    per-day limits survive across process runs.
Fail-closed everywhere: unknown model -> assume the priciest; unreadable ledger -> refuse.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from . import config

# USD per MILLION tokens (input, output). Approximate — verify against current Anthropic
# pricing; override PRICES if it drifts. Unknown model -> priciest, so we never UNDER-charge.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
}
_UNKNOWN_PRICE = (15.0, 75.0)

_ROOT = Path(__file__).resolve().parent.parent
_USE_CONFIG = object()   # sentinel: "read this cap from config" (distinct from None = "off")


def estimate_cost(model: str, in_tokens: int, out_tokens: int) -> float:
    pin, pout = PRICES.get(model, _UNKNOWN_PRICE)
    return round(in_tokens / 1e6 * pin + out_tokens / 1e6 * pout, 6)


@dataclass
class Reservation:
    ok: bool
    reason: str


class RateLimiter:
    def __init__(self, *, max_calls_per_run: int | None = None, max_calls_per_day: int | None = None,
                 max_usd_per_day: float | None = None, ledger_path: str | Path | None = None,
                 max_calls_per_user_per_day=_USE_CONFIG, max_usd_per_user_per_day=_USE_CONFIG):
        lim = config.LIMITS
        self.max_calls_per_run = lim["max_calls_per_run"] if max_calls_per_run is None else max_calls_per_run
        self.max_calls_per_day = lim["max_calls_per_day"] if max_calls_per_day is None else max_calls_per_day
        self.max_usd_per_day = lim["max_usd_per_day"] if max_usd_per_day is None else max_usd_per_day
        # Per-user caps: None means OFF, so the sentinel distinguishes "use config" from "off".
        self.max_calls_per_user_per_day = (lim["max_calls_per_user_per_day"]
            if max_calls_per_user_per_day is _USE_CONFIG else max_calls_per_user_per_day)
        self.max_usd_per_user_per_day = (lim["max_usd_per_user_per_day"]
            if max_usd_per_user_per_day is _USE_CONFIG else max_usd_per_user_per_day)
        p = lim["spend_ledger"] if ledger_path is None else ledger_path
        self.ledger_path = Path(p) if os.path.isabs(str(p)) else _ROOT / p
        self._run_calls = 0

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d")

    def _day_totals(self, user: "str | None" = None) -> tuple[int, float]:
        """(calls, usd) recorded today; if `user` is given, only that user's entries. Raises on
        a corrupt ledger — callers treat that as fail-closed (refuse to spend when we can't
        account for what's been spent)."""
        if not self.ledger_path.exists():
            return 0, 0.0
        calls, usd, today = 0, 0.0, self._today()
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not str(rec.get("ts", "")).startswith(today):
                continue
            if user is not None and rec.get("user") != user:
                continue
            calls += 1
            usd += float(rec.get("usd", 0.0))
        return calls, usd

    def reserve(self, estimated_usd: float = 0.0, user: "str | None" = None) -> Reservation:
        if self._run_calls >= self.max_calls_per_run:
            return Reservation(False, f"per-run call cap reached ({self.max_calls_per_run})")
        try:
            day_calls, day_usd = self._day_totals()
        except Exception as e:  # corrupt/unreadable ledger -> fail closed
            return Reservation(False, f"cannot read spend ledger, refusing to spend ({type(e).__name__})")
        if day_calls >= self.max_calls_per_day:
            return Reservation(False, f"daily call cap reached ({self.max_calls_per_day})")
        if day_usd + estimated_usd > self.max_usd_per_day:
            return Reservation(
                False,
                f"daily budget ${self.max_usd_per_day:.2f} would be exceeded "
                f"(spent ${day_usd:.4f} today + est ${estimated_usd:.4f} this call)",
            )
        # Per-user caps (opt-in): one user must not be able to spend the whole account's budget.
        if user is not None and (self.max_calls_per_user_per_day is not None
                                 or self.max_usd_per_user_per_day is not None):
            try:
                u_calls, u_usd = self._day_totals(user)
            except Exception as e:
                return Reservation(False, f"cannot read spend ledger, refusing to spend ({type(e).__name__})")
            if (self.max_calls_per_user_per_day is not None
                    and u_calls >= self.max_calls_per_user_per_day):
                return Reservation(False, f"per-user daily call cap reached "
                                          f"({self.max_calls_per_user_per_day}) for '{user}'")
            if (self.max_usd_per_user_per_day is not None
                    and u_usd + estimated_usd > self.max_usd_per_user_per_day):
                return Reservation(False, f"per-user daily budget ${self.max_usd_per_user_per_day:.2f} "
                                          f"would be exceeded for '{user}' (spent ${u_usd:.4f} today)")
        return Reservation(True, "ok")

    def record(self, model: str, in_tokens: int, out_tokens: int,
               user: "str | None" = None) -> float:
        usd = estimate_cost(model, in_tokens, out_tokens)
        self._run_calls += 1
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": user,
                "model": model, "in_tokens": in_tokens, "out_tokens": out_tokens, "usd": usd,
            }) + "\n")
        return usd

    def status(self, user: "str | None" = None) -> dict:
        try:
            day_calls, day_usd = self._day_totals()
        except Exception:
            day_calls, day_usd = -1, -1.0
        out = {
            "run_calls": self._run_calls,
            "max_calls_per_run": self.max_calls_per_run,
            "day_calls": day_calls,
            "max_calls_per_day": self.max_calls_per_day,
            "day_usd": round(day_usd, 4),
            "max_usd_per_day": self.max_usd_per_day,
            "usd_remaining_today": (round(self.max_usd_per_day - day_usd, 4) if day_usd >= 0 else None),
        }
        if user is not None:
            try:
                u_calls, u_usd = self._day_totals(user)
            except Exception:
                u_calls, u_usd = -1, -1.0
            out["user"] = user
            out["user_day_calls"] = u_calls
            out["user_day_usd"] = round(u_usd, 4)
            out["max_calls_per_user_per_day"] = self.max_calls_per_user_per_day
            out["max_usd_per_user_per_day"] = self.max_usd_per_user_per_day
        return out


# Process-wide limiter — one process == one "run", so _run_calls counts this run.
LIMITER = RateLimiter()
