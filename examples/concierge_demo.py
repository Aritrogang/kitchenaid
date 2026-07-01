"""Watch the Concierge route, govern cost, hold the session, and trace every handoff.

One Concierge instance, several turns. Notice: a plain dinner spins up 2 agents (no LLM, no
Shopper); only the shopping turn engages the Shopper; feedback attaches to the last meal.

    python3 examples/concierge_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.concierge import Concierge, format_trace
from kitchenaid.models import Profile
from kitchenaid.taste import TasteMemory

PROFILE = Profile.from_dict({"user_id": "d", "name": "Devon", "allergies": ["shellfish"],
                             "diet": "none", "budget_per_meal_usd": 6.0})
TASTE = TasteMemory()

TURNS = [
    "what should I make for dinner?",
    "what do I need to buy for dinner with rice?",
    "honestly that last one was too spicy and took too long",
    "plan my week",
]


def main():
    c = Concierge()
    for turn in TURNS:
        print("=" * 74)
        print(f'you: "{turn}"')
        r = c.handle(turn, PROFILE, taste=TASTE)
        print(r.message)
        print("  " + format_trace(r).replace("\n", "\n  "))
        print()
    print(f"[learned taste after feedback: spice_tolerance={TASTE.spice_tolerance}, "
          f"time_pref={TASTE.time_pref}]")


if __name__ == "__main__":
    main()
