"""CLI front door:  python -m kitchenaid "quick dinner, I have chicken and spinach"."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import agent
from .models import Profile

_DEFAULT_PROFILE = Path(__file__).resolve().parent / "data" / "profile.example.json"


def load_profile(path: str | None) -> Profile:
    p = Path(path) if path else _DEFAULT_PROFILE
    with open(p, encoding="utf-8") as f:
        return Profile.from_dict(json.load(f))


def _render(rec: agent.Recommendation, profile: Profile) -> str:
    out: list[str] = []
    m = rec.moment
    ctx = []
    if m.on_hand:
        ctx.append("on hand: " + ", ".join(m.on_hand))
    if m.time_available_min:
        ctx.append(f"~{m.time_available_min} min")
    if m.expiring:
        ctx.append("expiring: " + ", ".join(m.expiring))
    out.append(f"  [{profile.name} · {profile.diet} · "
               f"allergies: {', '.join(profile.allergies) or 'none'}]")
    if ctx:
        out.append("  [" + " · ".join(ctx) + "]")
    out.append("")

    if rec.chosen and rec.chosen_gate:
        out.append(f"{rec.chosen.name}  ({rec.chosen.cuisine})")
        for r in rec.why:
            out.append(f"    - {r}")
        if rec.chosen_gate.flags:
            out.append("    heads up:")
            for fl in rec.chosen_gate.flags:
                out.append(f"        - {fl}")
    else:
        out.append("Nothing in the corpus passes your hard rules for this moment.")

    if rec.rejected:
        out.append("")
        out.append(f"  Considered {rec.considered}, the Dietitian gate blocked:")
        for recipe, verdict in rec.rejected[:4]:
            out.append(f"    x {recipe.name}: {'; '.join(verdict.hard_violations)}")
    return "\n".join(out)


_DEMO = [
    ("Default profile (shellfish allergy)", None,
     "quick dinner, I've got chicken and spinach, 20 minutes"),
    ("Vegan", {"user_id": "u2", "name": "Ravi", "allergies": [], "diet": "vegan",
               "budget_per_meal_usd": 4.0, "equipment": ["stovetop", "pot", "wok", "pan"],
               "skill": "beginner", "weeknight_minutes": 30},
     "use up the fridge — I have lentils, carrots and onion"),
    ("Peanut allergy (SAFETY)", {"user_id": "u3", "name": "Mia", "allergies": ["peanut"],
                                 "diet": "vegetarian", "equipment": ["stovetop", "pot", "pan"],
                                 "skill": "beginner"},
     "something with noodles, quick"),
    ("Shellfish allergy", {"user_id": "u4", "name": "Theo", "allergies": ["shellfish"],
                           "diet": "pescatarian", "equipment": ["stovetop", "wok", "oven"],
                           "skill": "intermediate"},
     "dinner with rice"),
]


def run_demo() -> None:
    for title, prof_dict, query in _DEMO:
        profile = (Profile.from_dict(prof_dict) if prof_dict
                   else load_profile(None))
        rec = agent.recommend(query, profile)
        print("=" * 72)
        print(f"{title}\n  \"{query}\"")
        print("-" * 72)
        print(_render(rec, profile))
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kitchenaid", description="Your kitchen agent.")
    parser.add_argument("query", nargs="*", help='e.g. "quick dinner, I have chicken"')
    parser.add_argument("--profile", help="path to a profile JSON (default: example profile)")
    parser.add_argument("--demo", action="store_true", help="run canned scenarios")
    args = parser.parse_args(argv)

    if args.demo:
        run_demo()
        return 0

    if not args.query:
        parser.print_help()
        return 1

    profile = load_profile(args.profile)
    rec = agent.recommend(" ".join(args.query), profile)
    backend = "Claude" if os.environ.get("ANTHROPIC_API_KEY") else "deterministic"
    print(_render(rec, profile))
    print(f"\n  (chef backend: {backend})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
