"""Turn the chef loose and watch it meet its gate. Produces the resolution-miss DATASET.

  python3 examples/generative_chef_run.py [N]

With ANTHROPIC_API_KEY set, it asks a cheap model (Haiku) to INVENT N recipes with free-text
ingredients. Without a key it falls back to a SIMULATED generative chef — realistic messy
output authored to stress the resolver (genuine gaps, not cherry-picked) so you can verify
the instrument by hand before trusting a few hundred live samples.

For every ingredient string it logs the three-way outcome (resolved / unresolved /
misresolved) to eval/resolution_misses.jsonl, enforces the live invariant (an approved
recipe must be fully resolved), and prints a report.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import budget, chef, config, eval_resolution as ev
from kitchenaid.models import Moment, Profile

# Adversarial profile: vegan + milk allergy stresses dairy/animal modifiers the hardest.
PROFILE = Profile.from_dict({
    "user_id": "devon", "name": "Devon", "allergies": ["milk"], "diet": "vegan",
})

# A simulated generative chef asked for "vegan dinners, avoid milk." Deliberately realistic:
# canonical hits, near-miss synonyms (rice noodles, yellow onion, brown lentils), modifier
# gaps (vegan cheddar, vegan sausage, egg-free mayonnaise), modifier-respected resolves
# (vegan butter, low-sodium tamari, almond milk), and resolved-dairy traps (greek yogurt).
_SIMULATED = [
    {"name": "Simple Lentil Soup", "cuisine": "Mediterranean", "time_min": 35, "servings": 4,
     "ingredients": [{"item": "lentils", "grams": 300}, {"item": "carrot", "grams": 120},
                     {"item": "onion", "grams": 100}, {"item": "tomato", "grams": 150},
                     {"item": "garlic", "grams": 12}, {"item": "cumin", "grams": 6},
                     {"item": "olive oil", "grams": 15}, {"item": "vegetable broth", "grams": 600}]},
    {"name": "Creamy Cashew Alfredo", "cuisine": "Italian", "time_min": 25, "servings": 2,
     "ingredients": [{"item": "rice noodles", "grams": 200}, {"item": "cashew cream", "grams": 120},
                     {"item": "vegan butter", "grams": 30}, {"item": "fresh garlic", "grams": 15},
                     {"item": "nutritional yeast", "grams": 20}, {"item": "low-sodium tamari", "grams": 15},
                     {"item": "baby spinach", "grams": 100}]},
    {"name": "Chickpea Coconut Curry", "cuisine": "Indian", "time_min": 30, "servings": 3,
     "ingredients": [{"item": "chickpeas", "grams": 240}, {"item": "coconut milk", "grams": 200},
                     {"item": "yellow onion", "grams": 80}, {"item": "fresh ginger", "grams": 10},
                     {"item": "garlic", "grams": 12}, {"item": "curry powder", "grams": 12},
                     {"item": "cilantro", "grams": 10}]},
    {"name": "Vegan Mac & Cheese", "cuisine": "American", "time_min": 25, "servings": 4,
     "ingredients": [{"item": "elbow macaroni", "grams": 300}, {"item": "vegan cheddar", "grams": 150},
                     {"item": "almond milk", "grams": 250}, {"item": "dijon mustard", "grams": 10},
                     {"item": "garlic powder", "grams": 4}]},
    {"name": "Lentil Bolognese", "cuisine": "Italian", "time_min": 40, "servings": 4,
     "ingredients": [{"item": "brown lentils", "grams": 300}, {"item": "crushed tomatoes", "grams": 400},
                     {"item": "yellow onion", "grams": 100}, {"item": "carrot", "grams": 100},
                     {"item": "olive oil", "grams": 15}, {"item": "red wine", "grams": 60},
                     {"item": "garlic", "grams": 12}]},
    {"name": "Tofu Veggie Stir-Fry", "cuisine": "Chinese", "time_min": 20, "servings": 2,
     "ingredients": [{"item": "firm tofu", "grams": 250}, {"item": "broccoli florets", "grams": 150},
                     {"item": "red bell pepper", "grams": 120}, {"item": "soy sauce", "grams": 30},
                     {"item": "sesame oil", "grams": 10}, {"item": "fresh ginger", "grams": 8},
                     {"item": "scallions", "grams": 20}]},
    {"name": "Black Bean Tacos", "cuisine": "Mexican", "time_min": 20, "servings": 3,
     "ingredients": [{"item": "corn tortillas", "grams": 120}, {"item": "black beans", "grams": 200},
                     {"item": "avocado", "grams": 100}, {"item": "lime", "grams": 20},
                     {"item": "red onion", "grams": 50}, {"item": "cumin", "grams": 5},
                     {"item": "cilantro", "grams": 10}]},
    {"name": "Creamy Potato Leek Soup", "cuisine": "French", "time_min": 35, "servings": 4,
     "ingredients": [{"item": "potatoes", "grams": 400}, {"item": "leeks", "grams": 150},
                     {"item": "greek yogurt", "grams": 100}, {"item": "vegetable broth", "grams": 600},
                     {"item": "garlic", "grams": 12}, {"item": "thyme", "grams": 3}]},
    {"name": "Peanut Tofu Bowl", "cuisine": "Thai", "time_min": 25, "servings": 2,
     "ingredients": [{"item": "jasmine rice", "grams": 300}, {"item": "firm tofu", "grams": 200},
                     {"item": "peanut butter", "grams": 50}, {"item": "low-sodium soy sauce", "grams": 25},
                     {"item": "lime", "grams": 20}, {"item": "sriracha", "grams": 15},
                     {"item": "scallions", "grams": 20}]},
    {"name": "Vegan Sausage Penne", "cuisine": "Italian", "time_min": 30, "servings": 3,
     "ingredients": [{"item": "penne", "grams": 300}, {"item": "vegan sausage", "grams": 200},
                     {"item": "marinara", "grams": 250}, {"item": "garlic", "grams": 12},
                     {"item": "olive oil", "grams": 15}, {"item": "basil", "grams": 8}]},
    {"name": "Egg-Free Caesar Salad", "cuisine": "American", "time_min": 15, "servings": 2,
     "ingredients": [{"item": "romaine", "grams": 200}, {"item": "egg-free mayonnaise", "grams": 40},
                     {"item": "dijon", "grams": 8}, {"item": "capers", "grams": 15},
                     {"item": "croutons", "grams": 50}, {"item": "lemon", "grams": 20}]},
    {"name": "Coconut Yogurt Parfait", "cuisine": "American", "time_min": 5, "servings": 1,
     "ingredients": [{"item": "coconut yogurt", "grams": 150}, {"item": "fresh blueberries", "grams": 60},
                     {"item": "granola", "grams": 40}, {"item": "maple syrup", "grams": 15}]},
]


def _recipes():
    moment = Moment(meal_type="dinner")
    live = chef.generate_recipes(PROFILE, moment, n=int(sys.argv[1]) if len(sys.argv) > 1 else 12)
    if live:
        return live, f"LIVE (Claude · {config.MODELS['generate']})"
    missing = ", ".join(config.ai_status()["missing"]) or "live call failed (set KITCHENAID_DEBUG=1)"
    return [chef._recipe_from_generated(d, i) for i, d in enumerate(_SIMULATED)], f"SIMULATED — {missing}"


_SEV_MARK = {"ok": "✅", "low": "·", "medium": "⚠", "critical": "🚨"}


def main() -> None:
    recipes, source = _recipes()
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    print(f"Generative chef source: {source}")
    print(f"Profile: {PROFILE.name} · diet={PROFILE.diet} · allergies={PROFILE.allergies}")
    print(f"Run id: {run_id}\n")

    totals = {"resolved": 0, "unresolved": 0, "misresolved": 0}
    approved = 0
    seen = 0
    misses_written = 0

    for recipe in recipes:
        audit = ev.audit_recipe(recipe, PROFILE)   # raises if the live invariant is violated
        verdict = "✅ APPROVED" if audit.approved else "⛔ blocked"
        print("=" * 78)
        print(f"{recipe.name}   →   {verdict}")
        for c in audit.classifications:
            seen += 1
            totals[c.outcome] += 1
            target = c.canonical or "—"
            mod = f" [{c.modifier}]" if c.modifier else ""
            print(f"  {_SEV_MARK[c.severity]} {c.raw:<24}{mod:<14} {c.outcome:<11} → {target}")
        if not audit.approved:
            for v in audit.hard_violations[:3]:
                print(f"      ↳ {v}")
        approved += int(audit.approved)
        misses_written += ev.log_misses(audit, run_id)

    print("\n" + "#" * 78)
    print("RESOLUTION-MISS REPORT")
    print("#" * 78)
    print(f"dishes: {len(recipes)}   approved: {approved}/{len(recipes)}   "
          f"ingredient strings seen: {seen}")
    print(f"  resolved cleanly      : {totals['resolved']}")
    print(f"  unresolved (fail-safe): {totals['unresolved']}")
    print(f"  MISRESOLVED (unsafe)  : {totals['misresolved']}   "
          f"{'← none, resolver held' if totals['misresolved'] == 0 else '← INVESTIGATE'}")
    print(f"  misses written to dataset this run: {misses_written}")

    print("\nAccumulated dataset (eval/resolution_misses.jsonl):")
    s = ev.summarize()
    print(f"  total miss records (all runs): {s['records']}  ({s.get('distinct_strings', 0)} distinct strings)")
    print(f"  by outcome: {s.get('by_outcome', {})}")
    print(f"  modifier-prefixed gaps: {s.get('modifier_gaps', {})}")
    print("  most common missed strings:")
    for stringval, n in s.get("most_common", []):
        print(f"      {n:>2}×  {stringval}")
    if s.get("critical"):
        print(f"\n  🚨 CRITICAL (mis-resolutions) logged: {len(s['critical'])}")

    st = budget.LIMITER.status()
    print(f"\n💳 spend guardrail: {st['run_calls']}/{st['max_calls_per_run']} calls this run · "
          f"${st['day_usd']:.4f}/${st['max_usd_per_day']:.2f} today "
          f"({st['day_calls']}/{st['max_calls_per_day']} daily calls)")


if __name__ == "__main__":
    main()
