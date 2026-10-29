"""Run only the request-interpretation step on a set of cases, for one checkout.

Usage: CANDIDATE=<checkout> python interpret.py <cases.json> <out.json> [repeats]
Each case: {"id", "message", "history": [{"role","content"}...]}. Prints the routing fields.
No database, no answer generation. Keys come from the local test keyring; never printed.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path("C:/Users/porap/orca/workspaces/chat-bot-nutrition/main-3")
CANDIDATE = Path(os.environ["CANDIDATE"])
sys.path.insert(0, str(CANDIDATE / "backend"))
sys.path.insert(0, str(ROOT / "output/functional-fixes-release-20261022"))
from keyring import KeyRing  # noqa: E402

from app.services.nutrition import ProfileInput  # noqa: E402
from app.services.request_understanding import interpret_request  # noqa: E402

PROFILE = ProfileInput(sex="male", birth_year=2005, birth_month=1, height_cm=175, weight_kg=58,
                       activity_level="moderate", goal="bulk")
MODEL = "gemini-3.5-flash-lite"
cases = json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
out_path = Path(sys.argv[2])
repeats = int(sys.argv[3]) if len(sys.argv) > 3 else 1
ring = KeyRing(int(os.environ.get("KEY_START", "2")))
results = json.loads(out_path.read_text(encoding="utf8")) if out_path.exists() else {}
for rep in range(1, repeats + 1):
    for case in cases:
        key = f"{case['id']}-r{rep}"
        if key in results:
            continue
        while True:
            time.sleep(4)
            try:
                value, _usage = interpret_request(ring.client, model=MODEL, message=case["message"],
                                                  history=case.get("history", []), profile=PROFILE)
                rec = json.loads(value.model_dump_json())
                break
            except Exception as exc:  # keep every outcome
                code = getattr(exc, "code", None)
                if code == 429 and ring.rotate():
                    continue
                if code in (500, 503):
                    time.sleep(10)
                    continue
                rec = {"error": type(exc).__name__, "message": str(exc)[:200]}
                break
        results[key] = rec
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf8")
        fs = rec.get("food_suggestion")
        print(key, rec.get("task", rec.get("error")), "food_suggestion=" + (json.dumps(fs, ensure_ascii=False) if fs else "None"), flush=True)
