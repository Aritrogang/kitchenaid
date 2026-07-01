"""Watch the Shopper -> Dietitian re-verify loop.

Same over-budget salmon dish, same pantry, two users. The only difference is an allergy —
and it changes which substitution survives re-verification. That's the inter-agent
dependency: the Shopper proposes the cheapest swap, the Dietitian vetoes the unsafe one.

    python3 examples/shopping_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import data
from kitchenaid.dietitian import Dietitian
from kitchenaid.models import Profile
from kitchenaid.pantry import Pantry
from kitchenaid.shopper import Shopper

RECIPE = next(r for r in data.recipes() if r.id == "salmon-quinoa-bowl")
PANTRY = Pantry.from_dict({"olive oil": 200, "garlic": 50, "lemon": 40})
BUDGET = 3.0  # per serving


def run(label, profile):
    plan = Shopper().plan(RECIPE, PANTRY, profile, budget_per_serving=BUDGET)
    print("=" * 70)
    print(f"{label}  (budget ${BUDGET:.2f}/serving)")
    print(f"  dish after shopping: {', '.join(i.item for i in plan.recipe.ingredients)}")
    print(f"  grocery list (${plan.total_cost_usd:.2f} total, ${plan.cost_per_serving_usd:.2f}/serving):")
    for gi in plan.items:
        print(f"     {gi.grams:>5.0f} g  {gi.item:<16} ${gi.est_cost_usd:.2f}")
    if plan.substitutions:
        print("  ✅ substitutions applied (re-verified safe):")
        for s in plan.substitutions:
            print(f"     {s.original} → {s.replacement}  ({s.reason})")
    if plan.rejected_substitutions:
        print("  ⛔ substitutions the Dietitian vetoed:")
        for s in plan.rejected_substitutions:
            print(f"     {s.original} → {s.replacement}  ({s.reason})")
    print()


if __name__ == "__main__":
    run("No allergies", Profile.from_dict({"user_id": "a", "name": "A", "allergies": [], "diet": "none"}))
    run("Soy allergy", Profile.from_dict({"user_id": "b", "name": "B", "allergies": ["soy"], "diet": "none"}))
