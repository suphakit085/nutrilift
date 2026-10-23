"""Compare main vs branch interpreter probes: clarify readings and task changes."""
import json, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent
load = lambda n: {(d["id"], d["rep"]): d for d in map(json.loads, (HERE / n).read_text(encoding="utf8").splitlines())}
main, branch = load("main.jsonl"), load("branch.jsonl")
errs = {k: (main[k].get("error", "")[:60], branch[k].get("error", "")[:60]) for k in main if "error" in main[k] or "error" in branch.get(k, {})}
print("errors:", len(errs))
for k, v in sorted(errs.items()):
    print("  ", k, v)
reading = lambda d: (d.get("task"), d.get("missing")) if "error" not in d else ("error", None)
for name, data in (("main", main), ("branch", branch)):
    c = collections.Counter(reading(d)[1] for d in data.values() if reading(d)[0] == "clarify")
    print(name, "clarify readings:", dict(c), "of", len(data))
print("differences (id rep: main -> branch):")
for k in sorted(main):
    if k in branch and reading(main[k]) != reading(branch[k]):
        print("  ", k, reading(main[k]), "->", reading(branch[k]), branch[k].get("named"))
