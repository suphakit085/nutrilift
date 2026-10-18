"""Production UAT regressions: formatting requests must not become food bans."""
import csv
from copy import deepcopy

import pytest

from app.services import chat
from app.services.meal_plan import excluded_by, validate_day_plan
from app.services.menu_context import conversation_profile, menu_planning_options
from app.services.thai_text import normalize_thai
from tests.test_meal_plan import FOODS_CSV
from tests.test_profile_chat_context import saved

CUT_REQUEST = (
    "จากโปรไฟล์ของฉัน ช่วยจัดเมนูลดไขมัน 3 มื้อ ไม่ใช้อาหารเสริม "
    "ขอปริมาณอาหารและยอดพลังงานโปรตีนรวม"
)
ALLERGY_REQUEST = (
    "ช่วยจัดเมนูลดไขมัน 3 มื้อตามโปรไฟล์ ผมแพ้ถั่วและอาหารทะเล "
    "ไม่ใช้อาหารเสริม ขอชื่ออาหารและปริมาณชัดเจน"
)


@pytest.mark.parametrize("history,message,expected", [
    ([], CUT_REQUEST, {"ไม่ใช้อาหารเสริม"}),
    ([{"role": "user", "content": CUT_REQUEST}],
     "ขออีกแบบ ยังเอาแค่ 3 มื้อเท่านั้น และไม่กินไก่ ไม่เอาอาหารเสริม",
     {"ไม่ใช้อาหารเสริม", "ไม่กินไก่"}),
    ([], ("ช่วยจัดอาหารไทย 4 มื้อเพื่อรักษาน้ำหนักตามโปรไฟล์ งบ 120 บาทต่อวัน "
     "ไม่ใช้เวย์ ขอปริมาณและยอดสารอาหารรวม"), {"ไม่ใช้อาหารเสริม"}),
    ([], ALLERGY_REQUEST, {"แพ้ถั่ว", "แพ้อาหารทะเล", "ไม่ใช้อาหารเสริม"}),
    ([{"role": "user", "content": ALLERGY_REQUEST}],
     ("ผมแพ้นมวัวด้วย ขอจัดเมนูอีกแบบ 3 มื้อ ห้ามใช้นมวัวหรือเวย์ "
     "และยังแพ้ถั่วกับอาหารทะเลเหมือนเดิม"),
     {"แพ้ถั่ว", "แพ้อาหารทะเล", "แพ้นมวัว", "ไม่ใช้อาหารเสริม"}),
])
def test_production_requests_and_old_history_reach_real_planner(
    monkeypatch, history, message, expected,
):
    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        foods = list(csv.DictReader(handle))
    monkeypatch.setattr(chat, "all_foods", lambda *_: foods)
    profile = saved(goal="cut", restrictions=["แพ้ถั่ว", "แพ้อาหารทะเล"] if "แพ้" in message else [])
    original = deepcopy(profile)
    effective, _ = conversation_profile(profile, history, message)
    assert set(effective.restrictions) == expected
    options = menu_planning_options(history, message)
    plan = chat._run_menu_tool(None, effective, options)
    if "แพ้ถั่ว" in expected:
        assert plan["error"] == "ambiguous_allergy"
        assert "ถั่วลิสง" in plan["message"]
        assert profile == original
        return
    assert "error" not in plan, plan
    assert len(plan["meals"]) == options["meal_count"]
    validate_day_plan(plan, foods)
    assert all(not excluded_by(item, effective.restrictions)
               for meal in plan["meals"] for item in meal["items"])
    assert profile == original  # Temporary instructions never rewrite saved data.


@pytest.mark.parametrize("details", [
    "ขอปริมาณอาหารและยอดโปรตีนรวม", "ขอยอดพลังงานรวมกับปริมาณ",
    "พร้อมปริมาณอาหารและยอดสารอาหารรวม", "พร้อมทั้งยอดรวมและปริมาณ",
    "แสดงชื่ออาหารและปริมาณชัดเจน", "บอกพลังงานและโปรตีนรวม",
    "ระบุปริมาณกับไขมันรวม", "สรุปสารอาหารและยอดรวม",
    "ช่วยคำนวณพลังงานและโปรตีน", "ขอเมนูและปริมาณ",
])
@pytest.mark.parametrize("separator", [" ", " และ", "\n", ", "])
def test_details_after_exclusion_are_not_foods(details, separator):
    effective, _ = conversation_profile(saved(), [], "ไม่เอาอาหารเสริม" + separator + details)
    assert effective.restrictions == ["ไม่ใช้อาหารเสริม"]


@pytest.mark.parametrize("message,expected", [
    ("ไม่กินไก่ ขอปริมาณอาหารและยอดรวม", {"ไม่กินไก่"}),
    ("แพ้ถั่วและอาหารทะเล พร้อมชื่ออาหารและปริมาณ", {"แพ้ถั่ว", "แพ้อาหารทะเล"}),
    ("แพ้นมวัวหรือถั่ว ขอเมนูและยอดรวม", {"แพ้นมวัว", "แพ้ถั่ว"}),
    ("แพ้ถั่วรวมถึงอาหารทะเล ขอปริมาณ", {"แพ้ถั่ว", "แพ้อาหารทะเล"}),
    ("ผมงดไก่ ขอปริมาณ", {"ไม่กินไก่"}),
    ("งดไข่พร้อมยอดรวม", {"ไม่กินไข่"}),
    ("ขอเมนูงดไข่", {"ไม่กินไข่"}),
    ("ฉันงดถั่วเหลือง", {"แพ้ถั่วเหลือง"}),
    ("ผมจะงดไก่", {"ไม่กินไก่"}),
    ("วันนี้งดไข่", {"ไม่กินไข่"}),
    ("ผู้ออกกำลังกายงดไข่", {"ไม่กินไข่"}),
    ("แพ้ถั่วเหลือง ขอปริมาณนํ้าดื่มและยอดรวม", {"แพ้ถั่วเหลือง"}),
    ("ไม่​เอาอาหารเสริม ขอปริมาณอาหารและยอดรวม", {"ไม่ใช้อาหารเสริม"}),
])
def test_actual_exclusions_survive_request_boundaries(message, expected):
    for text in (message, normalize_thai(message)):
        effective, _ = conversation_profile(saved(), [], text)
        assert set(effective.restrictions) == expected


@pytest.mark.parametrize("message", [
    "จากโปรไฟล์ตอนนี้ ฉันควรกินพลังงานและโปรตีนวันละเท่าไร ใช้สูตรอะไร ขอแหล่งอ้างอิงด้วย",
    "ขอแหล่งอ้างอิงด้วย", "อยากได้แตงดองกับขิงดองในเมนู",
    "เมนูนี้ดูงดงาม",
])
def test_no_abstinence_instruction_inside_ordinary_thai_words(message):
    effective, _ = conversation_profile(saved(), [], message)
    assert effective.restrictions == []


@pytest.mark.parametrize("food", ["คื่นช่าย", "เห็ด", "ผลไม้ทุกชนิด", "ของหมัก", "ขอนขาว", "บอกฉ่อย"])
@pytest.mark.parametrize("ending", ["", " ขอปริมาณอาหารและยอดรวม", " พร้อมชื่ออาหารและปริมาณ"])
def test_unknown_allergy_still_blocks_menu_and_survives_reset(food, ending):
    disclosure = "ฉันแพ้" + food + ending
    p, _ = conversation_profile(saved(), [{"role": "user", "content": disclosure}],
        "กลับไปใช้โปรไฟล์ที่บันทึกล่าสุดทั้งหมด")
    assert any(r.startswith("ข้อจำกัดที่ยังไม่รองรับ:") for r in p.restrictions)
    assert chat._run_menu_tool(None, p, {})["error"] == "unsupported_menu_constraint"


def test_known_plus_unknown_allergies_are_not_dropped_by_food_list_or_request():
    p, _ = conversation_profile(saved(), [], "แพ้นมวัวหรือเห็ด ขอชื่ออาหารและปริมาณ")
    assert "แพ้นมวัว" in p.restrictions
    assert any("เห็ด" in r for r in p.restrictions)
    assert chat._run_menu_tool(None, p, {})["error"] == "unsupported_menu_constraint"


@pytest.mark.parametrize("gap", [" ", "\t", "\n", "  "])
@pytest.mark.parametrize("marker", ["allergic to", "allergy to"])
def test_unknown_supplement_allergy_with_whitespace_stays_blocking(marker, gap):
    history = [{"role": "user", "content": marker + gap + "supplements"}]
    p, _ = conversation_profile(saved(), history,
        "กลับไปใช้โปรไฟล์ที่บันทึกล่าสุดทั้งหมด")
    assert chat._run_menu_tool(None, p, {})["error"] == "unsupported_menu_constraint"


def test_details_do_not_clear_saved_or_user_allergies_and_assistant_cannot_add_them():
    profile = saved(restrictions=["วีแกน"])
    history = [{"role": "user", "content": "แพ้นมวัว ขอปริมาณอาหารและยอดรวม"},
               {"role": "assistant", "content": "แพ้ถั่ว ขอเมนู"}]
    p, _ = conversation_profile(profile, history, "ขออีกแบบ พร้อมยอดรวมและปริมาณ")
    assert set(p.restrictions) == {"วีแกน", "แพ้นมวัว"}
    fresh, _ = conversation_profile(profile, [], "ขอเมนูพร้อมยอดรวม")
    assert fresh == profile
