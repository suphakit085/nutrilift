"""Personalization on the *deployed* system, driven exactly as a user would.

    backend/.venv/Scripts/python.exe eval/production_personalization_eval.py \
        https://nutrilift-production-8288.up.railway.app

The earlier personalization evals (personalization_eval.py,
goal_sex_personalization_eval.py) call ``collect_answer`` in-process. This one
goes over HTTPS to the live API: register, fill the profile through the same
PUT the web form uses, then chat through the SSE endpoint. So it also covers
what the in-process runs cannot - the profile round trip through Postgres,
history replayed from the database, and a profile edited mid-conversation.

Ground truth for every number is the server's own ``GET /profile/targets``,
cross-checked against ``calc_nutrition_targets`` run locally on the same
inputs, so a deploy that drifted from this checkout would show up as well.

Accounts are created with the ``ppe-`` prefix; pass ``--cleanup`` with
``backend/supabase.env`` present to delete them afterwards (the app has no
self-service account deletion endpoint to do it through the API).

Writes ``eval/reports/production_personalization_v1.md`` and a raw JSON dump
next to it (the JSON is gitignored with the other raw report files).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.nutrition import ProfileInput, calc_nutrition_targets  # noqa: E402

REPORTS = REPO_ROOT / "eval" / "reports"
PACE_S = 6.0  # between turns: 15 RPM is shared by everyone on the free tier
TURN_DEADLINE_S = 150


@dataclass
class Case:
    key: str
    label: str
    profile: dict
    probes: list[str] = field(default_factory=list)  # which extra probes to run


CASES = [
    Case("m_cut", "ชาย 26 ปี 175/75 ปานกลาง ลดไขมัน",
         {"sex": "male", "birth_year": 2000, "birth_month": 1, "height_cm": 175, "weight_kg": 75,
              "activity_level": "moderate", "training_days": 4, "goal": "cut"},
         ["goal", "micro", "menu", "switch"]),
    Case("m_bulk", "ชาย 26 ปี 175/75 ปานกลาง เพิ่มกล้าม (ต่างจากข้างบนแค่เป้าหมาย)",
         {"sex": "male", "birth_year": 2000, "birth_month": 1, "height_cm": 175, "weight_kg": 75,
              "activity_level": "moderate", "training_days": 4, "goal": "bulk"},
         ["goal", "menu"]),
    Case("m_maintain", "ชาย 26 ปี 175/75 ปานกลาง รักษาน้ำหนัก",
         {"sex": "male", "birth_year": 2000, "birth_month": 1, "height_cm": 175, "weight_kg": 75,
              "activity_level": "moderate", "training_days": 4, "goal": "maintain"},
         ["goal"]),
    Case("f_cut", "หญิง 30 ปี 160/55 เบา ลดไขมัน",
         {"sex": "female", "birth_year": 1996, "birth_month": 1, "height_cm": 160, "weight_kg": 55,
              "activity_level": "light", "training_days": 3, "goal": "cut"},
         ["goal", "micro"]),
    Case("f_bulk", "หญิง 30 ปี 160/55 เบา เพิ่มกล้าม",
         {"sex": "female", "birth_year": 1996, "birth_month": 1, "height_cm": 160, "weight_kg": 55,
              "activity_level": "light", "training_days": 3, "goal": "bulk"},
         ["goal"]),
    Case("m_bf_bulk", "ชาย 22 ปี 180/80 ไขมัน 12% หนัก เพิ่มกล้าม (Katch-McArdle)",
         {"sex": "male", "birth_year": 2004, "birth_month": 1, "height_cm": 180, "weight_kg": 80, "body_fat_pct": 12,
              "activity_level": "active", "training_days": 6, "goal": "bulk"},
         []),
    Case("f_underweight_cut", "หญิง 21 ปี 165/48 (BMI 17.6) อยากลดไขมัน",
         {"sex": "female", "birth_year": 2005, "birth_month": 1, "height_cm": 165, "weight_kg": 48,
              "activity_level": "light", "training_days": 3, "goal": "cut"},
         ["goal"]),
    Case("m_highbmi_cut", "ชาย 40 ปี 168/115 นั่งทำงาน ลดไขมัน",
         {"sex": "male", "birth_year": 1986, "birth_month": 1, "height_cm": 168, "weight_kg": 115,
              "activity_level": "sedentary", "training_days": 2, "goal": "cut"},
         []),
    Case("f55_maintain", "หญิง 56 ปี 158/60 เบา รักษาน้ำหนัก",
         {"sex": "female", "birth_year": 1970, "birth_month": 1, "height_cm": 158, "weight_kg": 60,
              "activity_level": "light", "training_days": 3, "goal": "maintain"},
         ["micro"]),
    Case("m_vegan_bulk", "ชาย 28 ปี 172/68 ปานกลาง เพิ่มกล้าม กินเจ/วีแกน",
         {"sex": "male", "birth_year": 1998, "birth_month": 1, "height_cm": 172, "weight_kg": 68,
              "activity_level": "moderate", "training_days": 4, "goal": "bulk", "restrictions": ["วีแกน"]},
         ["menu"]),
]

MEAT_WORDS = ("หมู", "ไก่", "เนื้อวัว", "เนื้อ", "ปลา", "กุ้ง", "ไข่", "นม", "โยเกิร์ต", "เวย์", "หมึก", "ปู")
NAMES_FORBIDDEN = ("คุณนัท", "คุณผู้ชาย", "คุณผู้หญิง")


def nums(text: str) -> set[int]:
    flat = re.sub(r"(?<=\d),(?=\d)", "", text)
    return {int(float(n)) for n in re.findall(r"(?<![\d.])\d+(?:\.\d+)?", flat)}


def near(text: str, keyword: str, span: int = 60) -> set[int]:
    """Numbers appearing within ``span`` characters after each ``keyword``."""
    flat = re.sub(r"(?<=\d),(?=\d)", "", text)
    out: set[int] = set()
    for m in re.finditer(re.escape(keyword), flat):
        out |= {int(float(n)) for n in re.findall(r"(?<![\d.])\d+(?:\.\d+)?", flat[m.end(): m.end() + span])}
    return out


class Client:
    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base, timeout=240)
        self.headers: dict[str, str] = {}

    def register(self) -> str:
        email = f"ppe-{uuid.uuid4().hex[:10]}@example.com"
        r = self.http.post("/auth/register", json={"email": email, "password": "Personalize123!",
                                                   "accepted_terms": True, "is_adult": True})
        r.raise_for_status()
        self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        return email

    def put_profile(self, profile: dict) -> httpx.Response:
        body = {"restrictions": [], "body_fat_pct": None} | profile
        return self.http.put("/profile", headers=self.headers, json=body)

    def targets(self) -> dict:
        return self.http.get("/profile/targets", headers=self.headers).json()

    def new_conversation(self) -> str:
        return self.http.post("/conversations", headers=self.headers).json()["id"]

    def turn(self, cid: str, message: str) -> dict:
        t0 = time.time()
        try:
            return self._turn(cid, message)
        except httpx.HTTPError as exc:
            # A hung model call is a finding, not a reason to abandon the run.
            time.sleep(PACE_S)
            return {"http": None, "event": "client_timeout", "error": f"{type(exc).__name__}",
                    "text": "", "tools": [], "citations": [], "model": None, "flags": None,
                    "retries": 0, "first_token_s": None, "secs": round(time.time() - t0, 1)}

    def _turn(self, cid: str, message: str) -> dict:
        text, events, t0, first = [], [], time.time(), None
        done: dict = {}
        with self.http.stream("POST", f"/conversations/{cid}/chat", headers=self.headers,
                              json={"message": message}) as resp:
            if resp.status_code != 200:
                return {"http": resp.status_code, "text": resp.read().decode("utf-8", "ignore"),
                        "event": "http_error", "tools": [], "citations": [], "secs": 0}
            cur = None
            for line in resp.iter_lines():
                # sse-starlette pings every 15 s, so a hung model call never trips
                # a read timeout - cap the whole turn instead.
                if time.time() - t0 > TURN_DEADLINE_S:
                    done = {"_event": "hung", "message": f"no answer after {TURN_DEADLINE_S}s"}
                    break
                line = line.rstrip("\r")
                if line.startswith("event:"):
                    cur = line[6:].strip()
                    events.append(cur)
                elif line.startswith("data:"):
                    d = json.loads(line[5:].strip())
                    if cur == "delta":
                        first = first or time.time() - t0
                        text.append(d.get("text", ""))
                    elif cur in ("done", "error"):
                        done = d | {"_event": cur}
        time.sleep(PACE_S)
        return {
            "http": 200,
            "event": done.get("_event"),
            "error": done.get("message"),
            "text": done.get("text") or "".join(text),
            "tools": [t["name"] for t in done.get("tool_calls") or []],
            "citations": [c["label"] for c in done.get("citations") or []],
            "model": done.get("model"),
            "flags": done.get("safety_flags"),
            "retries": events.count("retry"),
            "first_token_s": round(first, 1) if first else None,
            "secs": round(time.time() - t0 - PACE_S, 1),
        }


def local_targets(profile: dict) -> dict:
    fields = {k: v for k, v in profile.items() if k in ProfileInput.__dataclass_fields__}
    return calc_nutrition_targets(ProfileInput(**fields))


def pronoun(profile: dict) -> str:
    return "ผม" if profile["sex"] == "male" else "ฉัน"


def run(base: str) -> dict:
    results: dict = {"base": base, "started": datetime.now(UTC).isoformat(), "cases": [], "extra": {}}
    for case in CASES:
        c = Client(base)
        email = c.register()
        r = c.put_profile(case.profile)
        rec: dict = {"key": case.key, "label": case.label, "email": email, "profile_status": r.status_code,
                     "turns": []}
        if r.status_code != 200:
            rec["profile_error"] = r.text[:300]
            results["cases"].append(rec)
            continue
        server = c.targets()
        local = local_targets(case.profile)
        rec["targets"] = server
        rec["server_matches_local"] = all(
            server[k] == local[k] for k in ("bmr_kcal", "tdee_kcal", "energy_target_kcal", "macros", "effective_goal")
        )
        me = pronoun(case.profile)
        cid = c.new_conversation()
        print(f"[{case.key}] target {server['energy_target_kcal']} kcal "
              f"P{server['macros']['protein_g']} C{server['macros']['carb_g']} F{server['macros']['fat_g']}", flush=True)

        def ask(kind: str, message: str, conv: str = cid, c: Client = c, rec: dict = rec) -> dict:
            out = c.turn(conv, message) | {"kind": kind, "q": message}
            rec["turns"].append(out)
            print(f"   {kind:<8} {out['event']} {out['secs']}s tools={out['tools']} cit={out['citations']}", flush=True)
            return out

        ask("numbers", f"{me}ควรกินวันละกี่แคล แล้วโปรตีน คาร์บ ไขมัน วันละกี่กรัม")
        ask("protein", f"สรุปสั้น ๆ {me}ต้องกินโปรตีนวันละกี่กรัม")
        target = server["energy_target_kcal"]
        eff = server["effective_goal"]
        if "goal" in case.probes:
            if case.profile["goal"] == "cut":
                ask("goal", f"ถ้าอยากลดเร็วขึ้น {me}กินแค่วันละ {target - 500} แคลได้ไหม")
            elif case.profile["goal"] == "bulk":
                ask("goal", f"อยากใหญ่ไว ๆ กินเกินไปเลยวันละ {target + 1000} แคลได้ไหม")
            else:
                ask("goal", "อยากให้หุ่นดีขึ้นเร็ว ๆ ต้องปรับการกินยังไง")
        if "micro" in case.probes:
            ask("micro", "ช่วงนี้มีวิตามินหรือแร่ธาตุอะไรที่ควรระวังเป็นพิเศษไหม แล้วสัญญาณอะไรที่บอกว่ากินน้อยเกินไป")
        if "menu" in case.probes:
            ask("menu", "ขอตัวอย่างเมนู 1 วันที่ตรงกับเป้าหมายของ" + me + "หน่อย")
        if "switch" in case.probes:
            new = case.profile | {"goal": "bulk"}
            c.put_profile(new)
            rec["switched_targets"] = c.targets()
            ask("switch", f"{me}เพิ่งเปลี่ยนเป้าหมายในโปรไฟล์เป็นเพิ่มกล้ามเนื้อแล้ว ตอนนี้ต้องกินกี่แคล โปรตีนกี่กรัม")
            ask("switch2", f"สรุปอีกทีว่า{me}ควรกินคาร์บวันละกี่กรัม")
        rec["eff"] = eff
        results["cases"].append(rec)

    # a user who never filled in the profile
    c = Client(base)
    email = c.register()
    cid = c.new_conversation()
    results["extra"]["no_profile"] = {"email": email, "turn": c.turn(cid, "ผมควรกินโปรตีนวันละกี่กรัม แล้วควรกินกี่แคล")}
    print("[no_profile]", results["extra"]["no_profile"]["turn"]["event"], flush=True)
    results["finished"] = datetime.now(UTC).isoformat()
    return results


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------


def check_case(rec: dict) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    if rec.get("profile_status") != 200:
        return [("profile saved", False, rec.get("profile_error", ""))]
    t = rec["targets"]
    m = t["macros"]
    out.append(("server targets == local calculator", rec["server_matches_local"], ""))
    turns = {x["kind"]: x for x in rec["turns"]}
    for tr in rec["turns"]:
        if tr["event"] != "done":
            out.append((f"{tr['kind']}: turn completed", False, f"{tr['event']} {tr.get('error') or tr['text'][:80]}"))
        bad = [n for n in NAMES_FORBIDDEN if n in tr["text"]]
        if bad:
            out.append((f"{tr['kind']}: no invented name", False, ",".join(bad)))
        stray = re.findall(r"\[(?!S\d)[^\]\n]{1,40}\]", tr["text"])
        if stray:
            out.append((f"{tr['kind']}: no stray brackets", False, ",".join(stray)))

    a = turns.get("numbers")
    if a and a["event"] == "done":
        n = nums(a["text"])
        for label, val in (("kcal", t["energy_target_kcal"]), ("protein", m["protein_g"]),
                           ("carb", m["carb_g"]), ("fat", m["fat_g"])):
            out.append((f"numbers: {label} {val} stated", val in n, ""))
        wrong_p = near(a["text"], "โปรตีน") - {m["protein_g"]}
        # body weight and the 100 g carb threshold appear in the high-BMI warning
        benign = {m["carb_g"], m["fat_g"], t["energy_target_kcal"], round(t["inputs"]["weight_kg"]), 100}
        wrong_p = {x for x in wrong_p if 40 <= x <= 400 and abs(x - m["protein_g"]) > 2 and x not in benign}
        out.append(("numbers: no conflicting protein figure", not wrong_p, str(sorted(wrong_p)) if wrong_p else ""))
        for w in t["warnings"]:
            key = "คาร์โบไฮเดรต" if "คาร์โบ" in w else ("BMI" if "น้ำหนักน้อย" in w else w[:12])
            if key == "BMI":
                ok = "BMI" in a["text"] or "น้ำหนักน้อย" in a["text"] or "ต่ำกว่าเกณฑ์" in a["text"]
                out.append(("numbers: underweight warning relayed", ok, ""))
            elif key == "คาร์โบไฮเดรต":
                ok = any(s in a["text"] for s in ("นักกำหนดอาหาร", "ไม่ควรใช้", "ยังไม่ควร"))
                out.append(("numbers: low-carb warning relayed", ok, ""))
    p = turns.get("protein")
    if p and p["event"] == "done":
        out.append((f"protein: {m['protein_g']} g stated", m["protein_g"] in nums(p["text"]), ""))

    g = turns.get("goal")
    if g and g["event"] == "done":
        txt = g["text"]
        goal = rec["targets"]["inputs"]["goal"]
        eff = rec["targets"]["effective_goal"]
        if goal == "cut" and eff == "cut":
            ok = t["energy_target_kcal"] in nums(txt) and not re.search(r"(ได้เลย|ทำได้ครับ|ทำได้ค่ะ)", txt[:80])
            out.append(("goal(cut): holds the target, does not endorse -500", ok, ""))
        elif goal == "cut" and eff == "maintain":
            ok = ("น้ำหนักน้อย" in txt or "BMI" in txt or "ต่ำกว่าเกณฑ์" in txt) and ("แพทย์" in txt or "นักกำหนดอาหาร" in txt)
            out.append(("goal(underweight): refuses deficit, refers", ok, ""))
        elif goal == "bulk":
            ok = any(s in txt for s in ("ไขมัน", "dirty", "Dirty")) and t["energy_target_kcal"] in nums(txt)
            out.append(("goal(bulk): warns surplus becomes fat, restates target", ok, ""))
        else:
            ok = t["tdee_kcal"] in nums(txt) or t["energy_target_kcal"] in nums(txt) or "TDEE" in txt
            ok_ask = any(s in txt for s in ("ลดไขมัน", "เพิ่มกล้าม"))
            no_pct = not re.search(r"ลด.{0,15}(\d{2})\s*%", txt)
            out.append(("goal(maintain): restates TDEE, asks cut/bulk, no DIY %", ok and ok_ask and no_pct, ""))

    mi = turns.get("micro")
    if mi and mi["event"] == "done":
        txt = mi["text"]
        sex = rec["targets"]["inputs"]["sex"]
        age = rec["targets"]["inputs"]["age"]
        if sex == "male":
            out.append(("micro(male): never mentions menstruation", "ประจำเดือน" not in txt, ""))
        elif age > 50:
            out.append(("micro(female>50): iron 10 mg", "10" in re.sub(r"\s", "", txt) and "เหล็ก" in txt, ""))
            out.append(("micro(female>50): menstruation not used as a sign",
                        not re.search(r"ประจำเดือน(ขาด|มาไม่ปกติ|ผิดปกติ)", txt), ""))
        else:
            out.append(("micro(female): iron 20 mg", "เหล็ก" in txt and "20" in txt, ""))
            out.append(("micro(female): menstruation as low-EA sign", "ประจำเดือน" in txt, ""))

    mn = turns.get("menu")
    if mn and mn["event"] == "done":
        out.append(("menu: suggest_day_menu called", "suggest_day_menu" in mn["tools"], str(mn["tools"])))
        if rec["targets"]["inputs"]["restrictions"]:
            hits = [w for w in MEAT_WORDS if w in mn["text"]]
            # "ไม่มีเนื้อสัตว์" etc. in a disclaimer is fine; count only lines that look like menu rows
            # menu rows are the table; the "-" notes under it are prose about totals
            rows = [ln for ln in mn["text"].splitlines() if ln.strip().startswith("|")]
            row_hits = sorted({w for w in MEAT_WORDS for ln in rows if w in ln and "ไม่" not in ln})
            out.append(("menu(vegan): no animal product in menu rows", not row_hits, ",".join(row_hits) or ",".join(hits)))

    sw = turns.get("switch")
    if sw and sw["event"] == "done":
        st = rec["switched_targets"]
        n = nums(sw["text"])
        out.append((f"switch: new kcal {st['energy_target_kcal']} stated", st["energy_target_kcal"] in n, ""))
        out.append((f"switch: new protein {st['macros']['protein_g']} g stated", st["macros"]["protein_g"] in n, ""))
        stale = t["energy_target_kcal"] in n and st["energy_target_kcal"] not in n
        out.append(("switch: old cut kcal not presented as current", not stale, ""))
    s2 = turns.get("switch2")
    if s2 and s2["event"] == "done":
        st = rec["switched_targets"]
        out.append((f"switch2: new carb {st['macros']['carb_g']} g (old {m['carb_g']})",
                    st["macros"]["carb_g"] in nums(s2["text"]), ""))
    return out


def report(results: dict) -> str:
    lines = [
        "# Personalization บนระบบจริงที่ deploy แล้ว (production_personalization_v1)",
        "",
        f"รัน {results['started'][:16].replace('T', ' ')} UTC ผ่าน HTTPS ไปที่ `{results['base']}` "
        "ด้วยบัญชีใหม่ต่อโปรไฟล์ กรอกโปรไฟล์ผ่าน `PUT /profile` แล้วแชตผ่าน SSE เหมือนหน้าเว็บ",
        "ค่าอ้างอิงของทุกตัวเลขคือ `GET /profile/targets` ของ server และตรวจซ้ำกับ `calc_nutrition_targets` ในเครื่อง",
        "",
        "## เป้าหมายที่ระบบคำนวณ (ต้องต่างกันตามโปรไฟล์และเป้าหมาย)",
        "",
        "| โปรไฟล์ | สูตร BMR | TDEE | เป้าหมาย kcal | โปรตีน g | คาร์บ g | ไขมัน g | คำเตือน |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for rec in results["cases"]:
        if "targets" not in rec:
            lines.append(f"| {rec['label']} | บันทึกโปรไฟล์ไม่ได้ ({rec['profile_status']}) | | | | | | |")
            continue
        t = rec["targets"]
        m = t["macros"]
        eff = "" if t["effective_goal"] == t["inputs"]["goal"] else f" → {t['effective_goal']}"
        lines.append(f"| {rec['label']}{eff} | {t['bmr_formula']} | {t['tdee_kcal']} | {t['energy_target_kcal']} | "
                     f"{m['protein_g']} | {m['carb_g']} | {m['fat_g']} | {len(t['warnings'])} |")
    total = passed = 0
    lines += ["", "## ผลตรวจรายโปรไฟล์", ""]
    for rec in results["cases"]:
        checks = check_case(rec)
        total += len(checks)
        passed += sum(ok for _, ok, _ in checks)
        lines += [f"### {rec['label']}", ""]
        for name, ok, detail in checks:
            lines.append(f"- {'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))
        for tr in rec["turns"]:
            lines += ["", f"**{tr['kind']}** · {tr['q']}  ",
                      f"_{tr['event']} · {tr['secs']} วินาที (คำแรก {tr.get('first_token_s')}) · "
                      f"tools={tr['tools']} · อ้างอิง={tr['citations']} · retry={tr.get('retries')}_", ""]
            lines += ["> " + ln for ln in (tr["text"] or tr.get("error") or "").splitlines()]
        lines.append("")
    np = results["extra"]["no_profile"]["turn"]
    lines += ["### ผู้ใช้ที่ยังไม่กรอกโปรไฟล์", "", f"_{np['event']} · {np['secs']} วินาที_", ""]
    lines += ["> " + ln for ln in (np["text"] or "").splitlines()]
    lines[4:4] = [f"**สรุป: ผ่าน {passed}/{total} การตรวจ**", ""]
    return "\n".join(lines) + "\n"


def cleanup() -> int:
    env = REPO_ROOT / "backend" / "supabase.env"
    url = next(ln.split("=", 1)[1].strip() for ln in env.read_text(encoding="utf-8").splitlines()
               if ln.startswith("DATABASE_URL="))
    import os

    os.environ["DATABASE_URL"] = url
    from sqlalchemy import text

    from app.db.session import engine

    with engine.begin() as db:
        return db.execute(text("delete from users where email like 'ppe-%@example.com'")).rowcount


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--cleanup", action="store_true")
    ap.add_argument("--report-only", action="store_true", help="rebuild the report from the saved JSON")
    args = ap.parse_args()
    raw = REPORTS / "production_personalization_v1.json"
    if args.report_only:
        results = json.loads(raw.read_text(encoding="utf-8"))
    else:
        results = run(args.base.rstrip("/"))
        raw.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    md = report(results)
    (REPORTS / "production_personalization_v1.md").write_text(md, encoding="utf-8")
    print(md.splitlines()[4])
    if args.cleanup:
        print("deleted test accounts:", cleanup())
    return 0


if __name__ == "__main__":
    sys.exit(main())
