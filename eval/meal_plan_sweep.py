"""Reproduce the 162-case menu sweep against knowledge/foods.csv.

Run from the repository root: backend/.venv/Scripts/python.exe eval/meal_plan_sweep.py
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.meal_plan import MealPlanError, build_day_plan  # noqa: E402
from app.services.nutrition import ProfileInput, calc_nutrition_targets  # noqa: E402

RESTRICTIONS = {
    "none": (),
    "halal": ("ฮาลาล",),
    "vegetarian": ("มังสวิรัติ",),
    "vegan": ("วีแกน",),
    "nut_allergy": ("แพ้ถั่ว",),
    "seafood_allergy": ("แพ้อาหารทะเล",),
    "dairy_allergy": ("แพ้นมวัว",),
    "vegetarian_nut_allergy": ("มังสวิรัติ", "แพ้ถั่ว"),
    "no_beef": ("ไม่กินเนื้อวัว",),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--details", action="store_true", help="show each missed case")
    args = parser.parse_args()
    with (ROOT / "knowledge" / "foods.csv").open(encoding="utf-8-sig", newline="") as handle:
        foods = list(csv.DictReader(handle))

    outcomes: Counter[tuple[str, str]] = Counter()
    for sex in ("male", "female"):
        for goal in ("cut", "bulk", "maintain"):
            profile = ProfileInput(
                sex=sex, birth_year=1998, birth_month=1,
                height_cm=175 if sex == "male" else 160,
                weight_kg=75 if sex == "male" else 55,
                activity_level="moderate", goal=goal,
            )
            nutrition = calc_nutrition_targets(profile)
            targets = {
                "kcal": nutrition["energy_target_kcal"],
                **{key: nutrition["macros"][key] for key in ("protein_g", "carb_g", "fat_g")},
            }
            for label, restrictions in RESTRICTIONS.items():
                for variant in (0, 1, 2):
                    try:
                        plan = build_day_plan(foods, targets, restrictions, variant)
                        outcome = "pass" if plan["within_tolerance"] else "miss"
                        if args.details and outcome == "miss":
                            print(sex, goal, label, variant, plan["deviation_pct"])
                    except MealPlanError:
                        outcome = "unavailable"
                        if args.details:
                            print(sex, goal, label, variant, "unavailable")
                    outcomes[label, outcome] += 1

    print(f"foods: {len(foods)}")
    for label in RESTRICTIONS:
        print(
            f"{label}: pass={outcomes[label, 'pass']}/18 "
            f"miss={outcomes[label, 'miss']} unavailable={outcomes[label, 'unavailable']}"
        )
    print(f"total: pass={sum(v for (_, result), v in outcomes.items() if result == 'pass')}/162")


if __name__ == "__main__":
    main()
