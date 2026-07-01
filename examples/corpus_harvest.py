"""Harvest a broad, real resolution-miss dataset to sharpen the corpus.

Repeated runs of one profile keep surfacing the same vocabulary. Real coverage comes from
variety, so this samples across several diets and meal types — that's what pulls in eggs,
meat, fish, oats, bread, and the long tail of pantry items a single vegan-dinner profile
never emits. Every generated recipe goes through the same audit (classify + gate + log),
under the spend guardrail.

    python3 examples/corpus_harvest.py [n_per_combo]   # default 12
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import budget, chef, eval_resolution as ev
from kitchenaid.models import Moment, Profile

# Diverse (profile, meal) combos — each surfaces a different slice of real vocabulary.
COMBOS = [
    ({"allergies": [], "diet": "none"}, "dinner"),
    ({"allergies": [], "diet": "none"}, "breakfast"),
    ({"allergies": ["milk"], "diet": "vegan"}, "dinner"),
    ({"allergies": ["wheat"], "diet": "none"}, "lunch"),
    ({"allergies": ["shellfish"], "diet": "pescatarian"}, "dinner"),
    ({"allergies": ["peanut", "tree_nut"], "diet": "vegetarian"}, "lunch"),
    ({"allergies": [], "diet": "none"}, "lunch"),
]


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    run_id = f"harvest-{time.strftime('%Y%m%d-%H%M%S')}"
    dishes = approved = seen = 0

    for i, (prof, meal) in enumerate(COMBOS):
        profile = Profile.from_dict({"user_id": f"h{i}", "name": "H", **prof})
        recipes = chef.generate_recipes(profile, Moment(meal_type=meal), n=n)
        tag = f"{prof['diet']}/{','.join(prof['allergies']) or 'no-allergy'}/{meal}"
        if not recipes:
            print(f"  · {tag:<34} — no live output (key/budget?); skipping")
            continue
        for r in recipes:
            audit = ev.audit_recipe(r, profile)
            ev.log_misses(audit, run_id)
            dishes += 1
            approved += int(audit.approved)
            seen += len(audit.classifications)
        print(f"  ✓ {tag:<34} — {len(recipes)} dishes")

    print("\n" + "#" * 74)
    print(f"HARVEST COMPLETE — {dishes} dishes, {seen} ingredient strings, "
          f"{approved} approved ({(approved / dishes * 100 if dishes else 0):.0f}%)")
    s = ev.summarize()
    print(f"miss records: {s['records']}  ·  distinct strings: {s.get('distinct_strings', 0)}  "
          f"·  outcomes: {s.get('by_outcome', {})}")
    print(f"MISRESOLVED (unsafe): {len(s.get('critical', []))}")
    print("\nTop 40 missed strings (the corpus-sharpening gap list):")
    for stringval, cnt in s.get("most_common", [])[:40]:
        print(f"   {cnt:>3}×  {stringval}")
    st = budget.LIMITER.status()
    print(f"\n💳 spend: {st['run_calls']} calls this run · ${st['day_usd']:.4f}/${st['max_usd_per_day']:.2f} today")


if __name__ == "__main__":
    main()
