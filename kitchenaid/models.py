"""Core data models (Phase 0 schema).

Plain stdlib dataclasses so the MVP runs with zero third-party dependencies. The field
shapes are the contract every later phase builds on; see docs/PHASE_0_DESIGN.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ingredient:
    item: str          # canonical key into nutrition.json / prices.json
    grams: float       # everything normalized to grams in Phase 1 (1 egg ~= 50g)


@dataclass
class Recipe:
    id: str
    name: str
    cuisine: str
    time_min: int
    servings: int
    skill: str                       # beginner | intermediate | advanced
    equipment: list[str]
    diet_tags: list[str]             # diets the recipe CLAIMS to satisfy (chef hint only;
                                     # the gate scans ingredients, it does not trust these)
    spice_level: int                 # 0-3
    ingredients: list[Ingredient]
    steps: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        return cls(
            id=d["id"],
            name=d["name"],
            cuisine=d.get("cuisine", ""),
            time_min=int(d["time_min"]),
            servings=int(d["servings"]),
            skill=d.get("skill", "beginner"),
            equipment=list(d.get("equipment", [])),
            diet_tags=list(d.get("diet_tags", [])),
            spice_level=int(d.get("spice_level", 0)),
            ingredients=[Ingredient(i["item"], float(i["grams"])) for i in d["ingredients"]],
            steps=list(d.get("steps", [])),
        )

    def to_dict(self) -> dict:
        """Round-trips with from_dict — used to persist the last meal (session) across turns."""
        return {
            "id": self.id, "name": self.name, "cuisine": self.cuisine,
            "time_min": self.time_min, "servings": self.servings, "skill": self.skill,
            "equipment": list(self.equipment), "diet_tags": list(self.diet_tags),
            "spice_level": self.spice_level,
            "ingredients": [{"item": i.item, "grams": i.grams} for i in self.ingredients],
            "steps": list(self.steps),
        }


_SKILL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}


@dataclass
class Profile:
    user_id: str
    name: str
    allergies: list[str]             # HARD RULE: keys into the allergen map
    diet: str = "none"               # HARD RULE: none|vegetarian|vegan|pescatarian|halal|kosher
    calories_target: int | None = None
    protein_target_g: int | None = None
    budget_per_meal_usd: float | None = None
    equipment: list[str] = field(default_factory=list)
    skill: str = "beginner"
    weeknight_minutes: int = 30
    dislikes: list[str] = field(default_factory=list)
    liked_dishes: list[str] = field(default_factory=list)     # Phase 4: -> embeddings
    disliked_dishes: list[str] = field(default_factory=list)  # Phase 4: -> embeddings

    @property
    def skill_rank(self) -> int:
        return _SKILL_RANK.get(self.skill, 0)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            user_id=d["user_id"],
            name=d.get("name", ""),
            allergies=[a.lower() for a in d.get("allergies", [])],
            diet=d.get("diet", "none").lower(),
            calories_target=d.get("calories_target"),
            protein_target_g=d.get("protein_target_g"),
            budget_per_meal_usd=d.get("budget_per_meal_usd"),
            equipment=list(d.get("equipment", [])),
            skill=d.get("skill", "beginner").lower(),
            weeknight_minutes=int(d.get("weeknight_minutes", 30)),
            dislikes=[x.lower() for x in d.get("dislikes", [])],
            liked_dishes=list(d.get("liked_dishes", [])),
            disliked_dishes=list(d.get("disliked_dishes", [])),
        )

    def to_dict(self) -> dict:
        """Round-trips with from_dict — the shape the store persists and the API returns."""
        return {
            "user_id": self.user_id,
            "name": self.name,
            "allergies": list(self.allergies),
            "diet": self.diet,
            "calories_target": self.calories_target,
            "protein_target_g": self.protein_target_g,
            "budget_per_meal_usd": self.budget_per_meal_usd,
            "equipment": list(self.equipment),
            "skill": self.skill,
            "weeknight_minutes": self.weeknight_minutes,
            "dislikes": list(self.dislikes),
            "liked_dishes": list(self.liked_dishes),
            "disliked_dishes": list(self.disliked_dishes),
        }


@dataclass
class Moment:
    """This meal's constraints — kept separate from the persistent profile."""
    meal_type: str = "dinner"
    time_available_min: int | None = None
    on_hand: list[str] = field(default_factory=list)
    expiring: list[str] = field(default_factory=list)
    servings: int = 2
    # The user's own words, kept verbatim so the ranker can honor what they actually asked for
    # (cuisine, dish type, ingredients, spice) — not just the structured fields parsed out above.
    query: str = ""


@dataclass
class GateResult:
    """The Dietitian's verdict on one candidate. Invariant: approved => no hard_violations."""
    recipe_id: str
    approved: bool
    hard_violations: list[str]       # allergen / diet — these block approval
    flags: list[str]                 # budget / macro / time / equipment / skill — informational
    calories_per_serving: float
    protein_per_serving_g: float
    cost_total_usd: float
    cost_per_serving_usd: float
