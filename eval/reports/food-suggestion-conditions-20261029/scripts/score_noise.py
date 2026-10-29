"""Score the interpretation runs against CRITERIA.md (C1, C2 and the C3 routing diff)."""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    p = HERE / name
    return json.loads(p.read_text(encoding="utf8")) if p.exists() else {}


def listed(rec, branch):
    fs = rec.get("food_suggestion")
    if not fs:
        return False
    return not (branch and fs.get("unsupported_conditions"))


def probe():
    main, branch = load("probe-main.json"), load("probe-branch.json")
    per = {}
    for arm, data, is_branch in (("main", main, False), ("branch", branch, True)):
        for key, rec in data.items():
            case = key.rsplit("-r", 1)[0]
            per.setdefault(case, {}).setdefault(arm, []).append(
                "E" if "error" in rec else ("L" if listed(rec, is_branch) else "-"))
    t = {arm: sum(v.get(arm, []).count("L") for k, v in per.items() if k.startswith("T")) for arm in ("main", "branch")}
    k = {arm: sum(v.get(arm, []).count("L") for k, v in per.items() if k.startswith("K")) for arm in ("main", "branch")}
    for case in sorted(per):
        print(case, "main", "".join(per[case].get("main", [])), "branch", "".join(per[case].get("branch", [])))
    print("C1 target list routes:", t, "pass" if t["branch"] <= 2 and t["branch"] < t["main"] else "FAIL")
    zero = [c for c in per if c.startswith("K") and per[c].get("branch", []).count("L") == 0]
    print("C2 keep list routes:", k, "zero:", zero, "pass" if k["branch"] >= k["main"] - 1 and not zero else "FAIL")
    conds = Counter(c for key, rec in branch.items() for c in ((rec.get("food_suggestion") or {}).get("unsupported_conditions") or []))
    print("branch unsupported_conditions:", dict(conds))


def real():
    main, branch = load(sys.argv[2]), load(sys.argv[3])
    fields = ("task", "personal_context", "medical_self_context", "missing_information", "goal",
              "output_format", "topic", "evidence_only")
    route, other = [], []
    for key in sorted(set(main) & set(branch)):
        a, b = main[key], branch[key]
        if "error" in a or "error" in b:
            other.append((key, "error", a.get("error"), b.get("error")))
            continue
        if listed(a, False) != listed(b, True):
            route.append((key, listed(a, False), listed(b, True), b.get("food_suggestion")))
        diffs = [f for f in fields if a.get(f) != b.get(f)]
        if bool(a.get("meal_split")) != bool(b.get("meal_split")):
            diffs.append("meal_split")
        if diffs:
            other.append((key, diffs, [a.get(f) for f in diffs], [b.get(f) for f in diffs]))
    print("C3 list-route changes:", len(route))
    for r in route:
        print("  ", json.dumps(r, ensure_ascii=False))
    print("C3 other routing differences:", len(other))
    for r in other:
        print("  ", json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    real()
