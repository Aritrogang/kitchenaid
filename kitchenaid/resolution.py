"""Ingredient resolution — the bridge between a free-text chef and the canonical gate.

The deterministic chef only emits canonical ingredient keys, so the gate never sees an
unknown. The moment a generative chef (Claude, Phase 3+) proposes free text — "vegan
butter", "low-sodium tamari", "Greek yogurt", "prawns" — those strings won't match the
canonical table and the gate's fail-closed default would reject perfectly valid meals.
This module normalizes free text to a canonical key BEFORE the gate runs.

Safety contract — direction matters:
  * NO loose substring matching. "vegan butter" must NEVER resolve to dairy "butter".
    Resolution is: normalize -> exact -> explicit synonym -> strip cooking qualifiers ->
    naive singularize -> UNRESOLVED. Substring containment is never used.
  * Identity-changing modifiers ("vegan", "plant-based", "dairy-free", "almond", "soy",
    "coconut", "cashew", ...) are NEVER stripped — they change allergen/diet facts.
  * Unresolved is a first-class result. The gate fails CLOSED on it for any active hard
    rule, rather than guessing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from . import data

# Cooking / grade descriptors that do NOT change an ingredient's allergen or diet identity.
# Deliberately excludes anything that changes identity (vegan, plant, dairy-free, almond,
# soy, coconut, cashew, oat, etc.) — stripping those would be a safety bug.
#
# DANGER LINE: every word here is stripped to reach the base ingredient, so every word here
# MUST be allergen-neutral — a descriptor of preparation, grade, cut, size, colour, texture,
# or variety that does NOT change what allergens or animal products the food contains. An
# allergen-inverting modifier ("vegan", "dairy-free", "egg-free", ...) must NEVER appear in
# this set — those are handled by the entirely separate free-from path below. (test_resolution
# pins this disjointness.)
_QUALIFIERS = {
    # prep / grade / size
    "low-sodium", "low sodium", "reduced-sodium", "reduced sodium", "no-salt-added",
    "organic", "fresh", "frozen", "raw", "cooked", "boneless", "skinless", "unsalted",
    "salted", "extra-virgin", "extra virgin", "free-range", "grass-fed", "large", "small",
    "medium", "chopped", "diced", "minced", "ground", "sliced", "shredded", "ripe", "baby",
    "plain", "natural", "whole", "lean", "boiled", "steamed", "roasted", "powder", "grated",
    "toasted", "pitted", "halved", "cubed", "dried", "canned",
    # colour / texture / variety (allergen-neutral)
    "yellow", "red", "green", "white", "brown", "firm", "extra-firm", "silken", "florets",
    "crushed", "jasmine", "basmati", "long-grain", "wild", "elbow", "cherry",
    # form / cut / prep nouns — allergen-neutral because the BASE carries the allergen
    # ("lemon juice"->lemon, "garlic cloves"->garlic, "salmon fillets"->salmon).
    "juice", "cloves", "clove", "fillet", "fillets", "zest", "thigh", "thighs", "breasts",
    "scrambled", "smoked", "sushi", "sushi-grade", "heirloom", "rolled", "sea", "kosher",
    "all-purpose", "old-fashioned", "root", "slice", "slices", "mixed", "steel-cut", "steel",
    "arborio", "extra", "cut", "flakes",
}

# Explicit synonyms: free-text -> canonical key. Safety-critical mappings live here so they
# are never left to fuzzy matching. The canonical target carries the correct allergen/diet
# facts (e.g. "vegan butter" -> a dairy-free entry; "prawns" -> a shellfish entry).
_SYNONYMS = {
    "shoyu": "soy sauce",
    "soya sauce": "soy sauce",
    "green onion": "scallion",
    "green onions": "scallion",
    "spring onion": "scallion",
    "spring onions": "scallion",
    "garbanzo beans": "chickpeas",
    "garbanzo": "chickpeas",
    "garbanzos": "chickpeas",
    "bell peppers": "bell pepper",
    "red bell pepper": "bell pepper",
    "green bell pepper": "bell pepper",
    "capsicum": "bell pepper",
    "prawn": "shrimp",
    "prawns": "shrimp",
    "shrimps": "shrimp",
    "almond": "almonds",
    "cashew": "cashews",
    "walnut": "walnuts",
    "scallions": "scallion",
    # variety / shape -> base (allergen-neutral)
    "rice": "white rice",
    "macaroni": "noodles",
    "penne": "noodles",
    "spaghetti": "noodles",
    "pasta": "noodles",
    "fusilli": "noodles",
    "rigatoni": "noodles",
    "linguine": "noodles",
    "penne pasta": "noodles",
    "farfalle": "noodles",
    "farfalle pasta": "noodles",
    "whole wheat spaghetti": "noodles",
    "dijon": "dijon mustard",
    "chicken": "chicken breast",
    # seasonings (allergen-neutral) — a compound like "salt and pepper" maps to a neutral
    # entry; both salt and pepper are allergen/diet-inert, so the gate outcome is unchanged.
    "sea salt": "salt", "kosher salt": "salt", "table salt": "salt",
    "salt and pepper": "salt", "salt and pepper to taste": "salt", "salt & pepper": "salt",
    "pepper": "black pepper", "ground black pepper": "black pepper",
    "cracked black pepper": "black pepper", "freshly ground black pepper": "black pepper",
    "red pepper flakes": "chili", "red chili flakes": "chili", "chili flakes": "chili",
    "crushed red pepper": "chili", "cayenne": "chili", "cayenne pepper": "chili",
    # dairy variants -> a milk-bearing entry (accuracy: EVERY cheese carries milk)
    "mayo": "mayonnaise",
    "parmesan": "parmesan cheese", "grated parmesan": "parmesan cheese",
    "parmigiano reggiano": "parmesan cheese",
    "pecorino": "cheese", "pecorino romano": "cheese", "pecorino romano cheese": "cheese",
    "cotija": "cheese", "cotija cheese": "cheese", "shredded cheese": "cheese",
    "grated cheese": "cheese", "fresh mozzarella": "mozzarella",
    "feta cheese crumbles": "feta cheese", "crumbled feta": "feta cheese",
    # bread / flour family -> wheat-bearing
    "whole grain bread": "bread", "whole wheat bread": "bread", "sourdough bread": "bread",
    "sourdough": "bread", "ciabatta bread": "bread", "ciabatta": "bread",
    "pita bread": "bread", "pita": "bread", "everything bagel": "bagel",
    "whole wheat tortillas": "tortilla", "whole wheat tortilla": "tortilla",
    "flour tortilla": "tortilla", "flour tortillas": "tortilla",
    "panko breadcrumbs": "breadcrumbs", "panko": "breadcrumbs", "all purpose flour": "flour",
    # seafood
    "ahi tuna": "tuna", "canned tuna in water": "tuna", "canned tuna": "tuna",
    # produce / other
    "kalamata olives": "olives", "black olives": "olives", "green olives": "olives",
    "romaine lettuce": "romaine", "butter lettuce": "lettuce", "iceberg lettuce": "lettuce",
    "corn kernels": "corn", "sweet corn": "corn", "roasted peanuts": "peanuts",
    "rolled oats": "oats", "shredded coconut": "coconut",
    "brown sugar": "sugar", "powdered sugar": "sugar", "granulated sugar": "sugar",
    "white sugar": "sugar", "marinara sauce": "marinara", "ginger root": "ginger",
    "mixed greens": "greens", "long grain rice": "white rice", "arborio rice": "white rice",
    "thai basil": "basil", "palm sugar": "sugar", "mozzarella cheese": "mozzarella",
    "tahini hummus": "hummus", "coconut flakes": "coconut", "white fish": "fish",
    "heavy cream": "cream", "sugar snap peas": "snap peas", "mixed berries": "berries",
    "tagliatelle pasta": "noodles", "whole wheat pita": "bread", "pizza crust": "pizza dough",
    "halloumi": "halloumi cheese", "queso fresco": "cheese", "american cheese": "cheese",
    "crema": "cream", "beef sirloin": "beef", "pork chops": "pork", "canadian bacon": "bacon",
    "breakfast sausage": "sausage",
}

# FREE-FROM synonyms: only consulted on the allergen-bearing path. Each maps a modifier-
# prefixed string to a canonical entry that genuinely SATISFIES the modifier (dairy-free,
# egg-free, ...). It is structurally impossible for these to reach the base animal entry,
# because the free-from path never strips the modifier. Keeping them in their own table is
# the point: "vegan/dairy-free/egg-free X" is a different ingredient than X.
_FREE_FROM_SYNONYMS = {
    "plant butter": "vegan butter",
    "plant-based butter": "vegan butter",
    "dairy-free butter": "vegan butter",
    "dairy free butter": "vegan butter",
    "vegan margarine": "vegan butter",
    "vegan cheddar": "vegan cheese",
    "dairy-free cheese": "vegan cheese",
    "dairy free cheese": "vegan cheese",
    "plant-based cheese": "vegan cheese",
    "vegan mozzarella": "vegan cheese",
    "plant-based sausage": "vegan sausage",
    "meatless sausage": "vegan sausage",
    "vegan sausages": "vegan sausage",
    "egg-free mayonnaise": "vegan mayo",
    "egg-free mayo": "vegan mayo",
    "eggless mayonnaise": "vegan mayo",
    "eggless mayo": "vegan mayo",
    "vegan mayonnaise": "vegan mayo",
}


@dataclass(frozen=True)
class Resolution:
    raw: str
    canonical: str | None        # None == unresolved (gate fails closed for active hard rules)
    method: str                  # exact | synonym | qualifier | singular | unresolved

    @property
    def resolved(self) -> bool:
        return self.canonical is not None


def _normalize(raw: str) -> str:
    # fold accents so "jalapeño" -> "jalapeno", "sautéed" -> "sauteed"
    s = "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c))
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\- ]+", " ", s)   # drop punctuation but keep hyphens
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_qualifiers(norm: str) -> str:
    """Remove leading/trailing cooking qualifiers without touching identity words. Longer
    qualifiers are tried first so a two-word one ("extra virgin") isn't pre-empted by a
    single word it contains ("extra")."""
    changed = True
    s = norm
    while changed:
        changed = False
        for q in sorted(_QUALIFIERS, key=len, reverse=True):
            for pat in (rf"^{re.escape(q)} ", rf" {re.escape(q)}$"):
                new = re.sub(pat, " ", s).strip()
                if new != s:
                    s, changed = new, True
    return re.sub(r"\s+", " ", s).strip()


def _singularize(norm: str) -> str:
    if norm.endswith("ies") and len(norm) > 4:
        return norm[:-3] + "y"
    if norm.endswith("es") and len(norm) > 3:
        return norm[:-2]
    if norm.endswith("s") and len(norm) > 2:
        return norm[:-1]
    return norm


def resolve(raw: str) -> Resolution:
    """Dispatch to one of two paths with OPPOSITE safety semantics — and crucially, the
    choice is made BEFORE any stripping, by looking for an allergen-inverting modifier:

      * free-from path  — the string starts with "vegan / dairy-free / egg-free / ...". Its
        identity is defined by that modifier, so it resolves ONLY via exact or free-from
        synonym; it NEVER strips the modifier to reach a base word. Else it fails closed.
        This is what makes "vegan butter -> dairy butter" structurally impossible.
      * descriptive path — colour / texture / variety / prep qualifiers are allergen-neutral,
        so they may be stripped freely to reach the base ingredient.
    """
    modifier, _base = detect_modifier(raw)
    if modifier:
        return _resolve_free_from(_normalize(raw), raw)
    return _resolve_descriptive(_normalize(raw), raw)


def _resolve_free_from(norm: str, raw: str) -> Resolution:
    """Allergen-bearing path. Exact / free-from-synonym only — no qualifier stripping, ever."""
    if norm in data.ingredient_attrs():
        return Resolution(raw, norm, "exact")
    if norm in _FREE_FROM_SYNONYMS:
        return Resolution(raw, _FREE_FROM_SYNONYMS[norm], "synonym")
    return Resolution(raw, None, "unresolved")


def _resolve_descriptive(norm: str, raw: str) -> Resolution:
    """Descriptive path. Free to strip colour/texture/variety/prep qualifiers to the base."""
    table = data.ingredient_attrs()
    # 1. exact canonical match
    if norm in table:
        return Resolution(raw, norm, "exact")
    # 2. explicit synonym
    if norm in _SYNONYMS:
        return Resolution(raw, _SYNONYMS[norm], "synonym")
    # 3. strip descriptive qualifiers, retry exact + synonym
    stripped = _strip_qualifiers(norm)
    if stripped != norm:
        if stripped in table:
            return Resolution(raw, stripped, "qualifier")
        if stripped in _SYNONYMS:
            return Resolution(raw, _SYNONYMS[stripped], "qualifier")
    # 4. naive singularize, retry exact + synonym
    sing = _singularize(stripped)
    if sing != stripped:
        if sing in table:
            return Resolution(raw, sing, "singular")
        if sing in _SYNONYMS:
            return Resolution(raw, _SYNONYMS[sing], "singular")
    # 5. give up — fail closed downstream. NEVER fall back to substring matching.
    return Resolution(raw, None, "unresolved")


def resolve_attrs(raw: str) -> dict | None:
    """Resolve free text to canonical attributes, or None if unresolvable."""
    r = resolve(raw)
    return data.lookup_ingredient(r.canonical) if r.canonical else None


# --- modifier awareness --------------------------------------------------------------
# A "free-from" / plant modifier INVERTS the allergen+diet profile of the base word:
# "vegan butter" must not carry milk; "dairy-free X" must not carry dairy. These are the
# highest-risk strings to resolve, because getting the direction wrong silently approves an
# unsafe meal. Each modifier declares what it must EXCLUDE. (A modifier can still ADD
# allergens — e.g. vegan cheese is often cashew-based — so this only asserts exclusions.)
_INVERTING_MODIFIERS: dict[str, dict[str, set]] = {
    "vegan":         {"allergens": {"milk", "egg", "fish", "shellfish"}, "props": {"animal", "dairy", "egg"}},
    "plant-based":   {"allergens": {"milk", "egg", "fish", "shellfish"}, "props": {"animal", "dairy", "egg"}},
    "plant based":   {"allergens": {"milk", "egg", "fish", "shellfish"}, "props": {"animal", "dairy", "egg"}},
    "dairy-free":    {"allergens": {"milk"}, "props": {"dairy"}},
    "dairy free":    {"allergens": {"milk"}, "props": {"dairy"}},
    "non-dairy":     {"allergens": {"milk"}, "props": {"dairy"}},
    "egg-free":      {"allergens": {"egg"}, "props": {"egg"}},
    "eggless":       {"allergens": {"egg"}, "props": {"egg"}},
    "nut-free":      {"allergens": {"peanut", "tree_nut"}, "props": set()},
    "gluten-free":   {"allergens": {"wheat"}, "props": set()},
    "wheat-free":    {"allergens": {"wheat"}, "props": set()},
}


def detect_modifier(raw: str) -> tuple[str | None, str | None]:
    """Return (modifier, base) if the string is prefixed by an inverting modifier."""
    norm = _normalize(raw)
    for mod in sorted(_INVERTING_MODIFIERS, key=len, reverse=True):
        if norm == mod or norm.startswith(mod + " "):
            return mod, norm[len(mod):].strip()
    return None, None


def violates_modifier(modifier: str, canonical: str | None) -> bool:
    """True if `canonical` carries something the modifier promised to exclude. This is the
    mis-resolution detector — the live-fire alarm for the substring bug in disguise."""
    excl = _INVERTING_MODIFIERS.get(modifier)
    if not excl or not canonical:
        return False
    attrs = data.lookup_ingredient(canonical) or {}
    if excl["allergens"] & set(attrs.get("allergens", [])):
        return True
    if excl["props"] & set(attrs.get("diet_props", [])):
        return True
    return False


@dataclass(frozen=True)
class Classification:
    raw: str
    outcome: str           # "resolved" | "unresolved" | "misresolved"
    canonical: str | None
    modifier: str | None
    severity: str          # "ok" | "low" | "medium" | "critical"
    note: str


def classify(raw: str) -> Classification:
    """Three-way classification of a free-text ingredient string, with severity:

      resolved     — maps to a canonical entry (and, if modifier-prefixed, respects it). ok.
      unresolved   — no canonical match; the gate fails closed. SAFE but a false-reject.
                     low severity normally; MEDIUM if modifier-prefixed (a high-value gap
                     category — a plant/free-from variant the table is missing).
      misresolved  — resolved to an entry that VIOLATES its modifier (e.g. "vegan butter"
                     -> dairy "butter"). CRITICAL: this would approve an unsafe meal.
    """
    res = resolve(raw)
    modifier, _ = detect_modifier(raw)

    if res.canonical:
        if modifier and violates_modifier(modifier, res.canonical):
            return Classification(raw, "misresolved", res.canonical, modifier, "critical",
                                  f"'{modifier}' string resolved to '{res.canonical}', which carries an excluded property")
        note = "modifier respected" if modifier else res.method
        return Classification(raw, "resolved", res.canonical, modifier, "ok", note)

    if modifier:
        return Classification(raw, "unresolved", None, modifier, "medium",
                              f"modifier-prefixed ('{modifier}') with no canonical variant — fail closed (high-risk gap)")
    return Classification(raw, "unresolved", None, None, "low", "no canonical match — fail closed")
