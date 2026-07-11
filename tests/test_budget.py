"""Spend-guardrail tests — prove the cap blocks BEFORE money is spent, fails closed, and
the daily window is real. Runs with no key (the limiter is pure).

Standalone:  python3 tests/test_budget.py
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.budget import RateLimiter, estimate_cost  # noqa: E402


def _limiter(**kw):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    os.remove(path)  # start with no ledger
    kw.setdefault("ledger_path", path)
    return RateLimiter(**kw), path


# --- cost estimation -----------------------------------------------------------------

def test_estimate_cost_math():
    # Haiku (1.0 in / 5.0 out per Mtok): 1M in + 1M out = $6.00
    assert estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == 6.0


def test_unknown_model_priced_as_most_expensive():
    # fail-safe: an unknown model must never be UNDER-charged
    assert estimate_cost("some-future-model", 1_000_000, 0) == 15.0


# --- reserve blocks at each cap ------------------------------------------------------

def test_per_run_call_cap_blocks():
    lim, _ = _limiter(max_calls_per_run=2, max_calls_per_day=999, max_usd_per_day=999)
    assert lim.reserve().ok
    lim.record("claude-haiku-4-5-20251001", 10, 10)
    lim.record("claude-haiku-4-5-20251001", 10, 10)
    r = lim.reserve()
    assert r.ok is False and "per-run" in r.reason


def test_daily_usd_cap_blocks_before_spending():
    lim, _ = _limiter(max_calls_per_run=999, max_calls_per_day=999, max_usd_per_day=0.01)
    # a call estimated at 2 cents must be refused under a 1-cent daily cap
    r = lim.reserve(estimated_usd=0.02)
    assert r.ok is False and "daily budget" in r.reason


def test_daily_call_cap_blocks():
    lim, path = _limiter(max_calls_per_run=999, max_calls_per_day=1, max_usd_per_day=999)
    lim.record("claude-haiku-4-5-20251001", 10, 10)   # 1 call today
    r = lim.reserve()
    assert r.ok is False and "daily call cap" in r.reason


def test_under_all_caps_is_allowed():
    lim, _ = _limiter(max_calls_per_run=5, max_calls_per_day=5, max_usd_per_day=1.0)
    assert lim.reserve(estimated_usd=0.001).ok is True


# --- daily window is real ------------------------------------------------------------

def test_yesterdays_spend_does_not_count_today():
    lim, path = _limiter(max_calls_per_run=999, max_calls_per_day=1, max_usd_per_day=999)
    yesterday = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 86400))
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": yesterday, "model": "x", "in_tokens": 1, "out_tokens": 1, "usd": 0.5}) + "\n")
    # yesterday's call must not consume today's cap of 1
    assert lim.reserve().ok is True


# --- fail closed on a corrupt ledger -------------------------------------------------

def test_corrupt_ledger_fails_closed():
    lim, path = _limiter()
    with open(path, "w", encoding="utf-8") as f:
        f.write("this is not json\n")
    r = lim.reserve()
    assert r.ok is False and "cannot read spend ledger" in r.reason


def test_record_persists_and_accumulates():
    lim, path = _limiter()
    usd = lim.record("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert usd == 6.0
    calls, total = lim._day_totals()
    assert calls == 1 and total == 6.0


# --- per-user caps (opt-in) ----------------------------------------------------------

def test_per_user_usd_cap_blocks_that_user_only():
    lim, _ = _limiter(max_calls_per_run=999, max_calls_per_day=999, max_usd_per_day=999,
                      max_usd_per_user_per_day=0.01)
    lim.record("claude-haiku-4-5-20251001", 1_000_000, 1_000_000, user="alice")   # $6 for alice
    r = lim.reserve(estimated_usd=0.001, user="alice")
    assert r.ok is False and "per-user daily budget" in r.reason and "alice" in r.reason
    assert lim.reserve(estimated_usd=0.001, user="bob").ok is True                 # bob unaffected


def test_per_user_call_cap_blocks():
    lim, _ = _limiter(max_calls_per_run=999, max_calls_per_day=999, max_usd_per_day=999,
                      max_calls_per_user_per_day=1)
    lim.record("claude-haiku-4-5-20251001", 10, 10, user="alice")
    r = lim.reserve(user="alice")
    assert r.ok is False and "per-user daily call cap" in r.reason


def test_no_user_context_skips_per_user_caps():
    lim, _ = _limiter(max_calls_per_run=999, max_calls_per_day=999, max_usd_per_day=999,
                      max_usd_per_user_per_day=0.0001)
    assert lim.reserve(estimated_usd=1.0, user=None).ok is True    # CLI / unattributed call


def test_per_user_caps_off_by_default():
    lim, _ = _limiter(max_calls_per_run=999, max_calls_per_day=999, max_usd_per_day=999)
    lim.record("claude-haiku-4-5-20251001", 1_000_000, 1_000_000, user="alice")
    assert lim.reserve(estimated_usd=0.001, user="alice").ok is True   # only the global cap binds


def test_global_cap_still_binds_across_users():
    lim, _ = _limiter(max_calls_per_run=999, max_calls_per_day=999, max_usd_per_day=6.0,
                      max_usd_per_user_per_day=999)
    lim.record("claude-haiku-4-5-20251001", 1_000_000, 1_000_000, user="alice")   # $6 -> account full
    r = lim.reserve(estimated_usd=0.5, user="bob")                                # bob under his cap
    assert r.ok is False and "daily budget" in r.reason           # but the account is at its cap


def test_day_totals_filters_by_user():
    lim, _ = _limiter()
    lim.record("claude-haiku-4-5-20251001", 1_000_000, 1_000_000, user="alice")   # $6
    lim.record("claude-haiku-4-5-20251001", 1_000_000, 0, user="bob")             # $1
    assert lim._day_totals() == (2, 7.0)          # global
    assert lim._day_totals("alice") == (1, 6.0)   # alice only
    assert lim._day_totals("bob") == (1, 1.0)     # bob only


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} budget tests passed.")


if __name__ == "__main__":
    _run_standalone()
