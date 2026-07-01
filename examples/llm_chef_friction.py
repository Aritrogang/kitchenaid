"""Watch the resolution layer earn its keep.

The deterministic chef only emits canonical ingredients, so the gate never sees an unknown.
A *generative* chef (Claude) emits free text — "vegan butter", "low-sodium tamari",
"Greek yogurt", "prawns", "artisanal dragon glaze". This script simulates that output and
shows, ingredient by ingredient, how each string resolves and how the gate then rules.

    python3 examples/llm_chef_friction.py

Two things to notice:
  1. Good free text resolves to the RIGHT canonical entry (vegan butter -> dairy-free).
  2. Genuinely unknown text stays unresolved and the gate fails CLOSED for active hard rules.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.models import Ingredient, Profile, Recipe
from kitchenaid.resolution import resolve
from kitchenaid.tools import gate

# A "generative chef" proposal: a vegan dish written in natural, messy language.
PROPOSALS = [
    ("Creamy Vegan Pasta",
     ["noodles", "vegan butter", "cashew cream", "fresh garlic", "low-sodium tamari"]),
    ("Yogurt Herb Bowl (mislabeled 'vegan' by the chef)",
     ["white rice", "Greek yogurt", "baby spinach", "olive oil"]),
    ("Mystery Special",
     ["chickpeas", "artisanal dragon glaze", "onion"]),
]

PROFILE = Profile.from_dict({
    "user_id": "demo", "name": "Devon", "allergies": ["milk"], "diet": "vegan",
})


def main() -> None:
    print(f"User: {PROFILE.name}  ·  diet={PROFILE.diet}  ·  allergies={PROFILE.allergies}\n")
    for name, raw_items in PROPOSALS:
        print("=" * 72)
        print(f"Chef proposes: {name}")
        print("  ingredient resolution:")
        for raw in raw_items:
            r = resolve(raw)
            target = r.canonical if r.canonical else "✗ UNRESOLVED (fail closed)"
            print(f"    {raw:<26} → {target:<22} [{r.method}]")

        recipe = Recipe(id="x", name=name, cuisine="", time_min=15, servings=2,
                        skill="beginner", equipment=[], diet_tags=["vegan"], spice_level=0,
                        ingredients=[Ingredient(i, 60) for i in raw_items])
        verdict = gate(recipe, PROFILE)
        if verdict.approved:
            print(f"  GATE: ✅ approved  (~${verdict.cost_per_serving_usd:.2f}/serving, "
                  f"{verdict.calories_per_serving:.0f} kcal)")
        else:
            print("  GATE: ⛔ blocked")
            for v in verdict.hard_violations:
                print(f"          – {v}")
        print()

    backend = "Claude" if os.environ.get("ANTHROPIC_API_KEY") else "(simulated — no API key)"
    print(f"chef backend that would emit this free text in production: {backend}")


if __name__ == "__main__":
    main()
