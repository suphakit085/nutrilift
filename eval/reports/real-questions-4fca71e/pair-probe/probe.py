"""Interpreter-only live probe: probe.py <worktree> <out.jsonl> <reps>.

Runs interpret_request on all 61 real questions (once) and the pair cases below
(<reps> times) with the final arm's sample profile, so main and the branch can
be compared on task / missing_information.
"""
import json, os, sys, time
from pathlib import Path
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
MAIN3 = HERE.parents[2]
ARM = MAIN3 / "output/real-questions-final-4fca71e"
WT = Path(sys.argv[1]).resolve()
os.environ["GEMINI_API_KEY"] = dotenv_values(MAIN3 / "output/prompt-functional-fixes-20261022/test-api.env")["GEMINI_API_KEY"]
os.environ.setdefault("DATABASE_URL", "postgresql://unused:unused@localhost/unused")
sys.path.insert(0, str(WT / "backend"))
from google import genai
from app.services import request_understanding as ru
from app.services.nutrition import ProfileInput

assert str(WT) in ru.__file__
real = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
last = [0.0]


class M:
    def generate_content_stream(self, **kw):
        w = 6.5 - (time.monotonic() - last[0])
        if w > 0:
            time.sleep(w)
        last[0] = time.monotonic()
        yield from real.models.generate_content_stream(**kw)


PAIR_CASES = {
    "P01": "เวย์ทานคู่กับ .. !!",
    "P02": "กินครีเอทีนคู่กับ ... ได้ไหมครับ",
    "P03": "เวย์ผสมกับอะไรดี",
    "P04": "ข้าวกล้องกับข้าวขาว อันไหนดีกว่าสำหรับลดไขมัน",
    "P05": "หลังเล่นเวทควรกินไข่หรืออกไก่ดีครับ",
    "P06": "กินเวย์คู่กับนมได้ไหม",
}
profile = ProfileInput(**json.loads((ARM / "condition.json").read_text(encoding="utf8"))["profile"])
items = [(json.loads(l)["id"], json.loads(l)["question"], 1) for l in (ARM / "dataset.jsonl").read_text(encoding="utf8").splitlines() if l.strip()]
items += [(k, q, int(sys.argv[3])) for k, q in PAIR_CASES.items()]
out = Path(sys.argv[2])
done = {(json.loads(l)["id"], json.loads(l)["rep"]) for l in out.read_text(encoding="utf8").splitlines()} if out.exists() else set()
client = type("C", (), {"models": M()})()
for cid, question, reps in items:
    for rep in range(1, reps + 1):
        if (cid, rep) in done:
            continue
        entry = {"id": cid, "rep": rep, "worktree": WT.name}
        try:
            v, _ = ru.interpret_request(client, model="gemini-3.5-flash-lite", message=question, history=[], profile=profile)
            entry.update(task=v.task, missing=v.missing_information, named=getattr(v, "named_items", None))
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            if "RESOURCE_EXHAUSTED" in entry["error"] and "PerDay" in entry["error"]:
                print("daily quota exhausted; stopping", flush=True)
                sys.exit(2)
        with out.open("a", encoding="utf8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(cid, rep, entry.get("task"), entry.get("missing"), entry.get("named"), entry.get("error", ""), flush=True)
