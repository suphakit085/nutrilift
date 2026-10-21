"""Regression for the remaining Q2/Q3/Q4 findings, using source food rows."""

import copy
import csv
import json
import re
from types import SimpleNamespace

import pytest

from app.api.chat import turn_events
from app.services import chat, prompts
from app.services.creatine_facts import creatine_necessity_reply
from app.services.food_preparation import food_preparation, ready_supplemental_carb
from app.services.meal_plan import plan_day_menu, validate_day_plan
from app.services.nutrition import ProfileInput, calc_nutrition_targets
from tests.test_chat_stream import CONV_ID, FakeSession, messages
from tests.test_meal_plan import FOODS_CSV


@pytest.fixture(scope="module")
def foods():
    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def adult(**changes):
    return ProfileInput(**{
        "sex": "male", "birth_year": 2000, "birth_month": 1,
        "height_cm": 175, "weight_kg": 70, "activity_level": "moderate",
        "goal": "maintain", **changes,
    })


@pytest.mark.parametrize("thai,english,category,state", [
    ("มันฝรั่ง", "Potato, fresh, raw", "หัวและมันต่าง ๆ", "raw"),
    ("บร็อคโคลี่", "Broccoli, fresh, raw", "ผัก", "raw"),
    ("ข้าวสวย", "", "ข้าว-แป้ง", "cooked"),
    ("ข้าวเจ้า, สุก", "", "ข้าว-แป้ง", "cooked"),
    ("อกไก่ไม่มีหนัง, ต้ม", "", "เนื้อสัตว์", "cooked"),
    ("เทมเป้สุก", "Tempeh, cooked", "โปรตีนพืช", "cooked"),
    ("มะละกอสุก", "Papaya, ripe", "ผลไม้", "as_recorded"),
    ("ก๋วยเตี๋ยวเส้นใหญ่, สด", "Noodle, rice, fresh", "ข้าว-แป้ง", "unknown"),
    ("เต้าหู้ขาวแข็ง", "Firm tofu", "โปรตีนพืช", "unknown"),
    ("ขนมปังโฮลวีท", "Bread, whole wheat", "ข้าว-แป้ง", "as_sold"),
    ("วัตถุดิบใหม่", "", "ข้าว-แป้ง", "unknown"),
    ("เนื้อไก่ต้ม", "Chicken, raw", "เนื้อสัตว์", "unknown"),
])
def test_recorded_state_is_not_invented_from_category_or_calories(thai, english, category, state):
    food = {"name_th": thai, "name_en": english, "category": category, "kcal": 100}
    before = copy.deepcopy(food)
    result = food_preparation(food)
    assert result["state"] == state and result["basis"] == "recorded_food_name"
    assert food == before
    assert ready_supplemental_carb(food) is (state in {"cooked", "as_sold"})


@pytest.mark.parametrize("goal", ["cut", "maintain", "bulk"])
@pytest.mark.parametrize("restrictions", [[], ["วีแกน"], ["วีแกน", "แพ้ถั่วลิสง"], ["แพ้อาหารทะเล"]])
def test_profiles_keep_source_arithmetic_and_ready_supplemental_staples(foods, goal, restrictions):
    profile = adult(goal=goal, restrictions=restrictions)
    target = calc_nutrition_targets(profile)
    requested = {"kcal": target["energy_target_kcal"],
                 **{key: target["macros"][key] for key in ("protein_g", "carb_g", "fat_g")}}
    source_before = copy.deepcopy(foods)
    plan = plan_day_menu(foods, requested, restrictions, meal_count=6, allow_extra_meals=False)
    sources = {(row["name_th"], row["source"]): row for row in foods}
    independent = dict.fromkeys(requested, 0.0)
    assert len(plan["meals"]) == 6
    for meal in plan["meals"]:
        assert meal["food_weight_g"] <= (350 if meal["kind"] == "supplemental" else 750)
        for item in meal["items"]:
            row = sources[(item["name_th"], item["source"])]
            assert item["preparation"] == food_preparation(row)
            if meal["kind"] == "supplemental" and item["role"] == "carb":
                assert ready_supplemental_carb(row)
                assert "เส้นใหญ่, สด" not in item["name_th"] and item["name_th"] != "มันฝรั่ง"
            for key in independent:
                amount = float(row[key]) * item["grams"] / float(row["serving_g"])
                assert item[key] == pytest.approx(amount, abs=.051)
                independent[key] += amount
    for key in independent:
        assert plan["totals"][key] == pytest.approx(independent[key], abs=.051)
    assert foods == source_before
    validate_day_plan(plan, foods)


def no_external_calls(monkeypatch, foods):
    def forbidden(*args, **kwargs):
        pytest.fail("Explicit menu and safety routes must not require the model/retrieval")
    monkeypatch.setattr(chat, "get_client", forbidden)
    monkeypatch.setattr(chat.retrieval, "search", forbidden)
    monkeypatch.setattr(chat, "all_foods", lambda _: foods)


def run(message, profile, **kwargs):
    return list(chat.stream_chat(SimpleNamespace(commit=lambda: None, rollback=lambda: None),
        user_message=message, profile=profile, **kwargs))


def test_underweight_warning_precedes_target_and_menu_without_duplicates(monkeypatch, foods):
    no_external_calls(monkeypatch, foods)
    p = adult(weight_kg=50, height_cm=175, goal="cut", activity_level="light")
    text = run("จากโปรไฟล์ผมอยากลดไขมัน ช่วยกำหนดแคลอรี่และจัดเมนู 3 มื้อ", p)[-1]["text"]
    assert text.index("BMI 16.3") < text.index("เป้าหมาย: พลังงาน") < text.index("| มื้ออาหาร")
    assert text.count("BMI 16.3") == 1
    assert "รักษาน้ำหนัก" in text and p.goal == "cut"


def test_budget_is_partial_even_when_nutrients_meet_target(monkeypatch, foods):
    no_external_calls(monkeypatch, foods)
    events = run("จัดเมนู 3 มื้อ งบ 120 บาทต่อวัน", adult())
    done = events[-1]
    assert done["model"] == "rule:verified_menu"
    assert done["tool_calls"][0]["status"] == "partial"
    assert next(e for e in events if e["type"] == "tool")["status"] == "partial"
    assert done["text"].index("ยังไม่ได้คำนวณราคา") < done["text"].index("| มื้ออาหาร")
    assert chat._tool_status("suggest_day_menu", {
        "meals": [{}], "within_tolerance": True, "budget_status": "not_calculated",
    }) == "partial"


@pytest.mark.parametrize("constraint", ["แพ้เห็ด", "ข้อจำกัดที่ยังไม่รองรับ: เห็ด"])
def test_unsupported_allergy_does_not_ask_user_to_repeat_it(monkeypatch, foods, constraint):
    no_external_calls(monkeypatch, foods)
    p = adult(restrictions=[constraint])
    done = run("ช่วยจัดเมนู 3 มื้อ", p)[-1]
    assert "เห็ด" in done["text"] and "ยังไม่มีตัวกรอง" in done["text"]
    assert "ระบุข้อจำกัดให้ชัดเจน" not in done["text"] and "ข้อจำกัดที่ยังไม่รองรับ:" not in done["text"]
    assert done["tool_calls"][0]["status"] == "error" and "| มื้ออาหาร" not in done["text"]
    assert p.restrictions == [constraint]


def test_medical_followup_keeps_refusal_but_not_the_long_unasked_feature_list(monkeypatch, foods):
    no_external_calls(monkeypatch, foods)
    text = run("งั้นโปรตีน 200 กรัมได้ไหม", adult(),
        history=[{"role": "user", "content": "ผมเป็นโรคไตระยะ 3"}])[-1]["text"]
    assert "อยู่นอกขอบเขต" in text and "แพทย์" in text and "200" not in text
    assert len(text) < 400 and "เรื่องที่ผมช่วยได้" not in text


def test_observed_unit_contamination_preserves_quantity_and_supported_citation():
    text = "โปรตีนต่อ 1 किलोग्राम และปริมาณ 20 ग्राम [S1]"
    cleaned = chat.clean_answer(text, [{"label": "S1"}])
    assert cleaned == "โปรตีนต่อ 1 กิโลกรัม และปริมาณ 20 กรัม [S1]"


def test_question_focus_limits_optional_detail_without_crossing_into_other_topics():
    necessity = prompts.answer_focus_th("มือใหม่ครีเอทีนจำเป็นไหม ต้องโหลดหรือไม่")
    dosage = prompts.answer_focus_th("ครีเอทีนโหลดขนาดกี่กรัมต่อวัน")
    assert necessity and "ไม่แจกขนาดใช้" in necessity
    assert dosage and "ไม่แจกขนาดใช้" not in dosage
    assert prompts.answer_focus_th("โปรตีนวันละเท่าไร")
    assert prompts.answer_focus_th("โปรตีนต่อวันแบ่งมื้อละเท่าไร") == ""
    assert prompts.answer_focus_th("ช่วยอธิบายใยอาหาร") == ""


@pytest.mark.parametrize("question", [
    "มือใหม่ครีเอทีนจำเป็นไหม ต้องโหลดหรือไม่ ขอหลักฐานด้วย",
    "ครีเอทีนต้องโหลดไหม", "Is creatine loading necessary?",
])
def test_necessity_faq_uses_the_actual_source_label_and_no_unasked_dosage(question):
    passages = [{"label": "S4", "document_slug": "creatine",
                 "content": "การโหลดเพื่อสะสมเร็วและไม่จำเป็นต้องโหลดเพื่อเพิ่มระดับสะสม",
                 "source_refs": ["ISSN 2017"]}]
    reply = creatine_necessity_reply(question, passages)
    assert "ไม่จำเป็นต้องโหลด" in reply and "[S4]" in reply
    assert "ไม่ได้พิสูจน์" in reply and "เท่ากัน" in reply
    assert not re.search(r"\d", reply.replace("[S4]", ""))
    assert "กิโลกรัม" not in reply


@pytest.mark.parametrize("passages", [
    [], [{"label": "S1", "document_slug": "other", "content": "ไม่จำเป็นต้องโหลด"}],
    [{"label": "S1", "document_slug": "creatine", "content": "ไม่มีข้อมูลเรื่องการโหลด"}],
])
def test_necessity_faq_never_fabricates_a_missing_reference(passages):
    assert creatine_necessity_reply("ครีเอทีนต้องโหลดไหม", passages) is None


def test_dose_or_comparison_questions_remain_on_the_model_path():
    passages = [{"label": "S1", "document_slug": "creatine",
                 "content": "ไม่จำเป็นต้องโหลด", "source_refs": ["ISSN 2017"]}]
    for question in [
        "ครีเอทีนโหลดขนาดกี่กรัม", "ครีเอทีนแบบไม่โหลดต่างจากโหลดอย่างไร",
        "ผมกินวีแกน ครีเอทีนจำเป็นไหม", "ครีเอทีนจำเป็นสำหรับผู้สูงอายุไหม",
        "ครีเอทีนชนิดใหม่จำเป็นไหม", "ครีเอทีนต้องโหลดก่อนฝึกไหม",
    ]:
        assert creatine_necessity_reply(question, passages) is None


def test_faq_stream_persists_the_used_retrieval_source_without_calling_provider(monkeypatch):
    citation = {"label": "S3", "title": "ครีเอทีน", "document_slug": "creatine",
                "source_refs": ["ISSN 2017"]}
    passage = SimpleNamespace(as_citation=lambda: citation,
        as_dict=lambda: {**citation, "content": "ไม่จำเป็นต้องโหลดเพื่อเพิ่มระดับสะสม"})
    def forbidden(*args, **kwargs):
        pytest.fail("A verified necessity FAQ does not need a provider")
    monkeypatch.setattr(chat.retrieval, "search", lambda *args: [passage])
    monkeypatch.setattr(chat, "get_client", forbidden)
    session = FakeSession()
    events = list(turn_events(lambda: session, conversation_id=CONV_ID,
        user_message="มือใหม่ครีเอทีนจำเป็นไหม ต้องโหลดหรือไม่", profile=None, history=[],
        use_rag=True, is_first_message=True, stream=chat.stream_chat))
    done = json.loads(events[-1]["data"])
    assert done["model"] == "rule:creatine_necessity" and done["citations"] == [citation]
    assert "[S3]" in messages(session, "assistant")[0].content
    assert messages(session, "assistant")[0].citations == [citation]
