"""Versioned application portion guardrails, separate from nutrient references.

These are transparent product defaults, NOT clinical portion recommendations.
The papers in docs/meal-plan-practicality-recommendation-2026-10-17.md motivate
meal/portion constraints; they do not establish the numeric limits below.
Dietitian review is pending. Source nutrient values and serving_g stay unchanged.
"""

from dataclasses import dataclass

from app.services.thai_text import normalize_thai

PORTION_POLICY_VERSION = "practicality-v3"


@dataclass(frozen=True)
class PortionPolicy:
    key: str
    min_g: float
    max_g: float
    preferred_min_g: float
    preferred_max_g: float
    step_g: float = 25.0


def portion_policy(food: dict, role: str) -> PortionPolicy:
    """Broad, auditable food-kind defaults; unknown kinds use a role fallback.

    Values refer to the food as recorded (never a cooked/raw conversion).
    A range is intersected with the meal slot bounds by the planner.
    """
    name = normalize_thai(str(food.get("name_th") or ""))
    category = str(food.get("category") or "")
    if category == "อาหารเสริม" and "ผง" in name:
        return PortionPolicy("protein-powder", 20, 70, 20, 40)
    if category == "น้ำมันและไขมัน":
        return PortionPolicy("added-fat", 2.5, 20, 5, 15, step_g=2.5)
    if role == "fat" and category == "ถั่วและเมล็ด":
        return PortionPolicy("nuts-seeds", 10, 60, 15, 35, step_g=5)
    if role == "protein":
        if category in {"โปรตีนพืช", "ถั่วและเมล็ด"}:
            return PortionPolicy("plant-protein", 75, 300, 100, 250)
        return PortionPolicy("main-protein", 50, 300, 75, 200)
    if role == "carb":
        if "ขนมปัง" in name:
            return PortionPolicy("bread", 50, 200, 50, 150)
        return PortionPolicy("starch", 75, 400, 100, 300)
    if role == "fruit":
        return PortionPolicy("fruit", 50, 300, 75, 200)
    if role == "vegetable":
        return PortionPolicy("vegetable", 50, 250, 75, 200)
    return PortionPolicy("role-fallback", 0, 110, 20, 80)
