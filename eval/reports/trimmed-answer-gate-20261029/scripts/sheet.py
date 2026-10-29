"""Merge both arms into one shuffled review sheet (arm hidden behind a code), plus a key file."""
import hashlib
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
exp = {c["id"]: c for c in json.loads((HERE.parent / "real-questions-final-c0201c3/expectations.json").read_text(encoding="utf8"))["cases"]}
W1 = {"expected": ["บอกว่าจำเป็นต้องกินเวย์หรือไม่ (ไม่จำเป็นถ้าได้โปรตีนพอจากอาหาร)", "ตอบเรื่องกินไข่ 5-6 ฟองแทน"], "must_not": ["แต่งข้อมูลความปลอดภัยของไข่ที่แหล่งไม่ได้ระบุ"]}
items, key = [], {}
for arm in ("main", "branch"):
    for p in sorted((HERE / arm).glob("*.json")):
        r = json.loads(p.read_text(encoding="utf8"))
        code = hashlib.sha256(f"{arm}/{p.stem}".encode()).hexdigest()[:6]
        key[code] = f"{arm}/{p.stem}"
        case = p.stem.rsplit("-r", 1)[0]
        e = W1 if case == "W1" else exp[case]
        av = r.get("answer_validation") or {}
        items.append({"code": code, "case": case, "question": r["question"], "expected": e.get("expected"),
                      "must_not": e.get("must_not"), "terminal": r["terminal_type"],
                      "trimmed": "ตัดข้อความบางส่วน" in (r.get("text") or ""),
                      "error": None if r["terminal_type"] == "done" else (r.get("terminal") or {}).get("code"),
                      "text": r.get("text") or (r.get("terminal") or {}).get("message")})
random.Random(29).shuffle(items)
items.sort(key=lambda x: x["case"])
(HERE / "sheet.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf8")
(HERE / "sheet-key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf8")
print(len(items))
