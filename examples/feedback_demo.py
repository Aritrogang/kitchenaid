"""Watch the system adapt. Same user, same request — the ranking shifts because feedback
moved the taste memory. This is the loop that makes kitchenaid adaptive rather than static.

    python3 examples/feedback_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import chef, data
from kitchenaid.models import Moment, Profile
from kitchenaid.taste import TasteMemory
from kitchenaid.taster import Taster

PROFILE = Profile.from_dict({"user_id": "d", "name": "Devon", "allergies": [], "diet": "none"})
MOMENT = Moment()


def top(mem, n=4):
    return [f"{r.name} ({mem.score(r):+.2f})" for r in chef.propose(PROFILE, MOMENT, taste=mem)[:n]]


def main():
    mem = TasteMemory()
    taster = Taster()
    print("Top picks (no taste history):")
    for line in top(mem):
        print(f"   {line}")

    taster.record(next(r for r in data.recipes() if r.id == "chickpea-spinach-curry"), "loved", mem)
    print("\nAfter Devon LOVED the Chickpea & Spinach Curry (Indian):")
    for line in top(mem):
        print(f"   {line}")

    taster.record(next(r for r in data.recipes() if r.id == "peanut-noodles"), "too spicy", mem)
    print("\nAfter Devon said the Spicy Peanut Noodles were TOO SPICY (spice tolerance drops):")
    for line in top(mem):
        print(f"   {line}")
    print(f"\n   [taste memory: cuisine={mem.cuisine}, spice_tolerance={mem.spice_tolerance}]")


if __name__ == "__main__":
    main()
