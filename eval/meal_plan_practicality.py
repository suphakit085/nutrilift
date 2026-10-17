"""Freeze cases and compare portion/balance behaviour without model or DB calls.

Run with the backend's Python, --backend-dir selects old or candidate code.
The JSON includes complete outputs, timings, failures and source file hashes.
Numeric portion defaults are application policies, not clinical validation.
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-dir", type=Path, required=True)
    parser.add_argument("--foods", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--write-cases", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.backend_dir.resolve()))
    from app.services.meal_plan import MealPlanError, build_day_plan, excluded_by
    from app.services.nutrition import ProfileInput, calc_nutrition_targets

    restrictions = {
        "none": [], "halal": ["ฮาลาล"], "vegetarian": ["มังสวิรัติ"],
        "vegan": ["วีแกน"], "nut_allergy": ["แพ้ถั่ว"],
        "seafood_allergy": ["แพ้อาหารทะเล"], "dairy_allergy": ["แพ้นมวัว"],
        "vegetarian_nut_allergy": ["มังสวิรัติ", "แพ้ถั่ว"], "no_beef": ["ไม่กินเนื้อวัว"],
    }
    if args.write_cases:
        cases = []
        for sex in ("male", "female"):
            for goal in ("cut", "bulk", "maintain"):
                profile = {"sex": sex, "goal": goal, "birth_year": 1998, "birth_month": 1,
                           "weight_kg": 75 if sex == "male" else 55,
                           "height_cm": 175 if sex == "male" else 160,
                           "activity_level": "moderate"}
                nutrition = calc_nutrition_targets(ProfileInput(**profile))
                targets = {"kcal": nutrition["energy_target_kcal"],
                           **{k: nutrition["macros"][k] for k in ("protein_g", "carb_g", "fat_g")}}
                for label, items in restrictions.items():
                    for variant in range(3):
                        for count in (3, 4):
                            cases.append({"id": f"{sex}-{goal}-{label}-v{variant}-m{count}",
                                          "profile": profile, "targets": targets, "restrictions": items,
                                          "variant": variant, "meal_count": count})
        args.cases.parent.mkdir(parents=True, exist_ok=True)
        args.cases.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    tracked = [args.backend_dir / "app/services/meal_plan.py",
               args.backend_dir / "app/services/meal_portions.py", args.foods, args.cases,
               Path(__file__)]
    hashes = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in tracked if p.exists()}
    with args.foods.open(encoding="utf-8-sig", newline="") as handle:
        foods = list(csv.DictReader(handle))
    by_name = {f["name_th"]: f for f in foods}
    results = []
    stats: Counter = Counter()
    for case in cases:
        start = time.perf_counter()
        record = {"id": case["id"], "meal_count": case["meal_count"]}
        try:
            plan = build_day_plan(foods, case["targets"], case["restrictions"],
                                  case["variant"], meal_count=case["meal_count"])
            record["plan"] = plan
            flat = [i for m in plan["meals"] for i in m["items"]]
            record["restriction_violations"] = sum(
                excluded_by(by_name[i["name_th"]], case["restrictions"]) is not None for i in flat)
            record["tiny_main_proteins"] = sum(
                i["role"] == "protein" and m["key"] != "snack" and i["grams"] < 50
                for m in plan["meals"] for i in m["items"])
            record["large_starches"] = sum(i["role"] == "carb" and i["grams"] > 400 for i in flat)
            shares = ([0.3, 0.35, 0.35] if case["meal_count"] == 3 else [0.25, 0.3, 0.3, 0.15])
            record["balanced"] = all(
                abs(m[k] / plan["totals"][k] - share) <= share * 0.25 + 0.001
                for m, share in zip(plan["meals"], shares, strict=True) for k in ("kcal", "protein_g"))
            record["protein_max_share"] = max(m["protein_g"] for m in plan["meals"]) / plan["totals"]["protein_g"]
            record["distribution_distance"] = sum(
                (m[k] / plan["totals"][k] - share) ** 2
                for m, share in zip(plan["meals"], shares, strict=True) for k in ("kcal", "protein_g"))
            stats[f"m{case['meal_count']}_daily_pass"] += plan["within_tolerance"]
            stats[f"m{case['meal_count']}_balanced"] += record["balanced"]
            for key in ("restriction_violations", "tiny_main_proteins", "large_starches"):
                stats[key] += record[key]
        except MealPlanError as exc:
            record["error"] = str(exc)
            stats["errors"] += 1
        record["seconds"] = round(time.perf_counter() - start, 4)
        results.append(record)
        if len(results) % 54 == 0:
            print(json.dumps({"progress": len(results), "total": len(cases)}), flush=True)
    output = {"recorded_at_utc": datetime.now(UTC).isoformat(), "case_count": len(cases),
              "summary": dict(stats), "results": results,
              "sha256": hashes,
              "sources_unchanged_during_run": all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
                                                  for p, digest in hashes.items())}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"]))


if __name__ == "__main__":
    main()
