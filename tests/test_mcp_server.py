"""Phase 5 tests — the MCP tool logic (dict-in/dict-out, no MCP SDK needed).

These verify the tools exposed over MCP delegate to the same deterministic core as the
in-process gate — including the safety guarantee.

Standalone:  python3 tests/test_mcp_server.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid import mcp_server  # noqa: E402


def _recipe_with(item):
    return {"id": "x", "name": "X", "cuisine": "", "time_min": 10, "servings": 1,
            "ingredients": [{"item": item, "grams": 100}]}


def test_verify_recipe_blocks_an_allergen():
    out = mcp_server.verify_recipe(_recipe_with("peanut butter"),
                                   {"user_id": "u", "name": "U", "allergies": ["peanut"], "diet": "none"})
    assert out["approved"] is False
    assert any("Peanut" in v for v in out["hard_violations"])


def test_verify_recipe_approves_safe():
    out = mcp_server.verify_recipe(_recipe_with("chickpeas"),
                                   {"user_id": "u", "name": "U", "allergies": ["peanut"], "diet": "vegan"})
    assert out["approved"] is True


def test_resolve_ingredient_reports_canonical_and_outcome():
    out = mcp_server.resolve_ingredient("extra virgin olive oil")
    assert out["canonical"] == "olive oil" and out["outcome"] == "resolved"
    miss = mcp_server.resolve_ingredient("artisanal dragon glaze")
    assert miss["outcome"] == "unresolved" and miss["canonical"] is None


def test_nutrition_and_cost_tools():
    r = _recipe_with("chicken breast")
    assert mcp_server.nutrition_of(r)["per_serving"]["protein_g"] > 0
    assert mcp_server.cost_of(r)["total_usd"] > 0


def test_tool_registry_exposes_four_tools():
    assert set(mcp_server.TOOLS) == {"verify_recipe", "resolve_ingredient", "nutrition_of", "cost_of"}


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} mcp tests passed.")


if __name__ == "__main__":
    _run_standalone()
