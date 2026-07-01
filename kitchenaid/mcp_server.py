"""MCP server (Phase 5) — exposes kitchenaid's deterministic tools over the Model Context
Protocol so any agent host (Claude Desktop, or the Concierge) can call them across a boundary.

The tool LOGIC lives in plain dict-in/dict-out functions below (fully testable without the
MCP SDK). The FastMCP wrapping is a thin adapter, guarded behind the import so the module
loads even when `mcp` isn't installed. Nothing here re-implements safety — each function
delegates to the same deterministic core (`tools`, `resolution`) that the gate uses, so the
MCP surface and the in-process agents share one source of truth.

Run the server (after `pip install mcp`):
    python3 -m kitchenaid.mcp_server
"""

from __future__ import annotations

from dataclasses import asdict

from . import resolution, tools
from .models import Moment, Profile, Recipe


# --- tool logic (pure, testable, no MCP dependency) ----------------------------------

def verify_recipe(recipe: dict, profile: dict, moment: dict | None = None) -> dict:
    """The Dietitian gate over MCP: does this recipe clear the user's hard rules?"""
    r = Recipe.from_dict(recipe)
    p = Profile.from_dict(profile)
    m = Moment(**moment) if moment else None
    return asdict(tools.gate(r, p, m))


def resolve_ingredient(name: str) -> dict:
    """Resolve a free-text ingredient to a canonical entry, with the three-way classification."""
    return asdict(resolution.classify(name))


def nutrition_of(recipe: dict) -> dict:
    """Deterministic per-serving + total macros for a recipe."""
    return tools.compute_nutrition(Recipe.from_dict(recipe))


def cost_of(recipe: dict) -> dict:
    """Estimated grocery cost for a recipe."""
    return tools.compute_cost(Recipe.from_dict(recipe))


TOOLS = {
    "verify_recipe": verify_recipe,
    "resolve_ingredient": resolve_ingredient,
    "nutrition_of": nutrition_of,
    "cost_of": cost_of,
}


# --- FastMCP wrapping (thin adapter, optional) ---------------------------------------

def build_server():
    """Construct the FastMCP server. Raises ImportError if the MCP SDK isn't installed."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("kitchenaid")

    @server.tool()
    def verify_recipe_tool(recipe: dict, profile: dict, moment: dict | None = None) -> dict:
        """Check a recipe against a user's allergies, diet, budget, and macro targets."""
        return verify_recipe(recipe, profile, moment)

    @server.tool()
    def resolve_ingredient_tool(name: str) -> dict:
        """Resolve a free-text ingredient string to a canonical entry (resolved/unresolved/misresolved)."""
        return resolve_ingredient(name)

    @server.tool()
    def nutrition_tool(recipe: dict) -> dict:
        """Compute per-serving and total macros for a recipe."""
        return nutrition_of(recipe)

    @server.tool()
    def cost_tool(recipe: dict) -> dict:
        """Estimate the grocery cost of a recipe."""
        return cost_of(recipe)

    return server


def main() -> None:
    try:
        server = build_server()
    except ImportError:
        raise SystemExit("MCP SDK not installed. Run: pip install mcp")
    server.run()


if __name__ == "__main__":
    main()
