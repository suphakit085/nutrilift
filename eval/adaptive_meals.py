"""Reproduce adaptive-menu behaviour on frozen targets, without network or DB.

Baseline uses the previous chat default (four meals); adaptive uses user options.
Food weights are source weights, not clinical meal-size recommendations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-dir", required=True, type=Path)
    parser.add_argument("--foods", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--write-cases", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.backend_dir.resolve()))
    from app.services import meal_plan
    from app.services.nutrition import ProfileInput, calc_nutrition_targets

    if args.write_cases:
        cases = []
        restrictions = {
            "none": [], "halal": ["ฮาลาล"], "vegetarian": ["มังสวิรัติ"], "vegan": ["วีแกน"],
            "nuts": ["แพ้ถั่ว"], "seafood": ["แพ้อาหารทะเล"], "milk": ["แพ้นมวัว"],
            "vegetarian-nuts": ["มังสวิรัติ", "แพ้ถั่ว"], "no-beef": ["ไม่กินเนื้อวัว"],
        }
        for sex in ("male", "female"):
            for goal in ("cut", "maintain", "bulk"):
                profile = {"sex": sex, "goal": goal, "birth_year": 1998, "birth_month": 1,
                           "height_cm": 175 if sex == "male" else 160,
                           "weight_kg": 75 if sex == "male" else 55, "activity_level": "moderate"}
                nutrition = calc_nutrition_targets(ProfileInput(**profile))
                targets = {"kcal": nutrition["energy_target_kcal"],
                           **{k: nutrition["macros"][k] for k in ("protein_g", "carb_g", "fat_g")}}
                for label, exclusions in restrictions.items():
                    cases.append({"id": f"{sex}-{goal}-{label}", "targets": targets,
                                  "restrictions": exclusions, "options": {}})
        high = {"kcal": 4238, "protein_g": 198, "carb_g": 639, "fat_g": 99}
        for count in (3, 4, 5, 6):
            cases.append({"id": f"high-request-{count}", "targets": high, "restrictions": [],
                          "options": {"meal_count": count}})
        cases.extend([
            {"id": "high-auto", "targets": high, "restrictions": [], "options": {}},
            {"id": "high-refuse-extras", "targets": high, "restrictions": [],
             "options": {"meal_count": 3, "allow_extra_meals": False, "suggest_extra_meals": False}},
            {"id": "no-eligible-protein", "targets": high, "restrictions": ["วีแกน", "แพ้ถั่ว"],
             "options": {}},
            {"id": "unreachable-protein", "targets": {**high, "protein_g": 900},
             "restrictions": [], "options": {}},
        ])
        args.cases.parent.mkdir(parents=True, exist_ok=True)
        args.cases.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    files = [args.backend_dir / "app/services" / f for f in
             ("meal_plan.py", "meal_portions.py", "menu_context.py", "chat.py")]
    files += [args.foods, args.cases, Path(__file__)]
    hashes = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    with args.foods.open(encoding="utf-8-sig", newline="") as handle:
        foods = list(csv.DictReader(handle))
    by_name = {f["name_th"]: f for f in foods}
    results, stats = [], Counter()
    for case in cases:
        start = time.perf_counter()
        record = {"id": case["id"]}
        try:
            if args.baseline:
                plan = meal_plan.build_day_plan(foods, case["targets"], case["restrictions"],
                                                meal_count=case["options"].get("meal_count", 4))
            else:
                plan = meal_plan.plan_day_menu(foods, case["targets"], case["restrictions"],
                                               **case["options"])
            meal_plan.validate_day_plan(plan, foods)
            record["plan"] = plan
            record["restriction_violations"] = sum(
                meal_plan.excluded_by(by_name[i["name_th"]], case["restrictions"]) is not None
                for m in plan["meals"] for i in m["items"])
            record["large_starches"] = sum(
                i["role"] == "carb" and i["grams"] > (200 if m["key"].startswith("snack") else 300)
                for m in plan["meals"] for i in m["items"])
            record["whole_egg_rows_without_units"] = sum(
                by_name[i["name_th"]]["category"] == "ไข่"
                and "ไข่ขาว" not in i["name_th"]
                and not meal_plan._is_countable(by_name[i["name_th"]])
                for m in plan["meals"] for i in m["items"])
            stats["daily_pass"] += plan["within_tolerance"]
            stats[f"selected_{plan['meal_count']}_meals"] += 1
            stats["with_alternative"] += bool(plan.get("extra_meal_options"))
            for key in ("restriction_violations", "large_starches", "whole_egg_rows_without_units"):
                stats[key] += record[key]
        except meal_plan.MealPlanError as exc:
            record["error"] = str(exc)
            stats["errors"] += 1
        record["seconds"] = round(time.perf_counter() - start, 4)
        results.append(record)
        if len(results) % 9 == 0:
            print(json.dumps({"progress": len(results), "total": len(cases)}), flush=True)
    output = {"recorded_at_utc": datetime.now(UTC).isoformat(), "case_count": len(cases),
              "mode": "baseline" if args.baseline else "adaptive", "summary": dict(stats),
              "sha256": hashes, "results": results,
              "sources_unchanged_during_run": all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h
                                                  for p, h in hashes.items())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"]))


if __name__ == "__main__":
    main()
