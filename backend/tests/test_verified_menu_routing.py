"""A model skipping or inventing a meal tool must never publish a fake plan."""
import csv
import json
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

from app.services import chat
from app.services.menu_request import next_menu_variant, requests_menu, unverified_menu_table
from app.services.nutrition import ProfileInput
from tests.test_chat_stream import CONV_ID, FakeSession, messages
from tests.test_meal_plan import FOODS_CSV


@pytest.fixture(scope="module")
def foods():
    with FOODS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def adult(**changes):
    return ProfileInput(**{
        "sex": "male", "birth_year": 2000, "birth_month": 1,
        "height_cm": 175, "weight_kg": 70, "goal": "maintain",
        "activity_level": "moderate", **changes,
    })


def no_model(monkeypatch, foods):
    def refuse(*args, **kwargs):
        pytest.fail("Explicit menu requests must not depend on the provider or retrieval")
    monkeypatch.setattr(chat, "get_client", refuse)
    monkeypatch.setattr(chat.retrieval, "search", refuse)
    monkeypatch.setattr(chat, "all_foods", lambda _: foods)


def run(message, profile, **kwargs):
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    return list(chat.stream_chat(db, user_message=message, profile=profile, **kwargs))


@pytest.mark.parametrize("message", [
    "จากน้ำหนักกับส่วนสูงในโปรไฟล์ ผมอยากลดไขมัน ช่วยกำหนดแคลอรี่และจัดเมนู 3 มื้อให้หน่อย",
    "ช่วยจัดอาหารไทย 4 มื้อเพื่อรักษาน้ำหนักตามโปรไฟล์ งบ 120 บาทต่อวัน ไม่ใช้เวย์",
    "ขอเมนู 3 มื้อ", "ช่วยแนะนำมื้ออาหารที่เหมาะกับเป้าหมาย", "สร้างตารางอาหาร",
    "วันนี้ควรกินอะไรบ้าง", "ขอตัวอย่างเมนู", "จัดแผนอาหารให้ฉัน",
    "Create a daily meal plan", "Can you give me a meal plan?", "suggest a menu",
    "อธิบายหลักการแล้วช่วยจัดเมนูให้ด้วย", "ขอหลักการจัดเมนูและช่วยจัดเมนูตัวอย่าง",
    "ตามโปรไฟล์ผมต้องกินเยอะ ช่วยจัดให้ครบเป้าหมายเพียง 2 มื้อต่อวันเท่านั้น ไม่เพิ่มมื้อ",
])
def test_explicit_request_routing(message):
    assert requests_menu(message, [])


@pytest.mark.parametrize("message", [
    "อธิบายวิธีจัดเมนูสำหรับเล่นเวท", "ขอหลักการวางแผนอาหาร", "ทำไมควรจัดอาหาร 3 มื้อ",
    "ไม่ต้องจัดเมนู ขอหลักการเฉยๆ", "แปลเมนูภาษาอังกฤษ", "เมนูโปรไฟล์อยู่ตรงไหน",
    "ข้าวมันไก่ 100 กรัมมีโปรตีนเท่าไร", "งานวิจัยการแบ่งอาหารสามมื้อกล่าวว่าอะไร",
    "How to create a meal plan?", "Don't create a menu; explain protein instead",
    "ขออีกแบบ", "ขอ 6 มื้อ", "เพิ่มมื้อเสริมได้",
    "ช่วยแนะนำเมนูโปรไฟล์", "ขอเมนูตั้งค่า",
    "ช่วยจัดโปรตีนเป็น 3 มื้อ",
])
def test_discussion_lookup_navigation_decline_and_context_free_followups_are_not_plans(message):
    assert not requests_menu(message, [])


@pytest.mark.parametrize("message", [
    "ขออีกแบบ ไม่กินไก่", "เพิ่มมื้อเสริมได้ตามเหมาะสม ขอเป็น 6 มื้อรวม",
    "เปลี่ยนใจ วันนี้กินได้แค่ 3 มื้อเท่านั้น ไม่เพิ่มมื้อเสริม ขอจัดใหม่",
    "ขออีกชุดที่ต่างจากเมื่อกี้", "ไม่เอามื้อเสริม", "another one please",
])
def test_only_user_menu_context_allows_a_followup(message):
    history = [{"role": "user", "content": "ขอเมนู 3 มื้อ"}]
    assert requests_menu(message, history)
    assert not requests_menu(message, [{"role": "assistant", "content": "ขอเมนู 3 มื้อ"}])
    assert not requests_menu(message, [*history, {"role": "user", "content": "ครีเอทีนจำเป็นไหม"}])


def test_latest_explicit_menu_choice_wins():
    assert not requests_menu("ขอเมนู แต่ไม่ต้องจัดเมนูแล้ว", [])
    assert requests_menu("ไม่ต้องจัดเมนู แต่เปลี่ยนใจขอเมนู", [])


@pytest.mark.parametrize("profile,message,count", [
    (adult(), "ช่วยจัดเมนู 3 มื้อ ไม่เอาอาหารเสริม", 3),
    (adult(goal="bulk"), "ช่วยจัดเมนูเพิ่มกล้าม 4 มื้อ ไม่เอาอาหารเสริม", 4),
    (adult(restrictions=["วีแกน", "แพ้นมวัว"]), "ขอเมนู 3 มื้อ", 3),
])
def test_menu_executes_without_model_and_keeps_verified_numbers(
    monkeypatch, foods, profile, message, count,
):
    no_model(monkeypatch, foods)
    events = run(message, profile)
    done = events[-1]
    assert done["type"] == "done" and done["model"] == "rule:verified_menu"
    assert done["tool_calls"][0]["status"] in {"success", "partial"}
    rows = [r for r in done["text"].splitlines() if r.startswith("| มื้อ") and "รายการอาหาร" not in r]
    assert len(rows) == count
    assert any(e["type"] == "tool" for e in events)
    assert done["usage"]["total_tokens"] == 0
    assert "ข้าวขาหมู" not in done["text"]


def test_original_underweight_uat_uses_maintenance_and_keeps_warning(monkeypatch, foods):
    no_model(monkeypatch, foods)
    p = adult(height_cm=180, weight_kg=50, activity_level="light", goal="cut")
    done = run("จากโปรไฟล์ผมอยากลดไขมัน ช่วยกำหนดแคลอรี่และจัดเมนู 3 มื้อ", p)[-1]
    assert done["tool_calls"][0]["status"] in {"success", "partial"}
    assert "2062 kcal" in done["text"] and "BMI 15.4" in done["text"]
    assert "ไม่กำหนดพลังงานขาดดุล" in done["text"]
    assert "ปรึกษาแพทย์" in done["text"] and "รักษาน้ำหนัก" in done["text"]
    assert "[S" not in done["text"]
    assert p.goal == "cut"


@pytest.mark.parametrize("message,profile,history", [
    ("โรคไตระยะ 3 ช่วยจัดเมนูเพิ่มกล้าม", adult(), []),
    ("ขอเมนูโปรตีน 200 กรัม", adult(), [{"role": "user", "content": "ผมเป็นโรคไต"}]),
    ("ขอเมนูวันละ 800 kcal", adult(), []),
    ("ช่วยจัดเมนูลดไขมัน", adult(birth_year=2012), []),
    ("กำลังตั้งครรภ์ ช่วยจัดเมนูลดไขมัน", adult(), []),
])
def test_safety_precedes_operations_even_with_provider_unavailable(
    monkeypatch, message, profile, history,
):
    def refuse(*args, **kwargs):
        pytest.fail("Safety refusal must precede foods, retrieval and provider")
    monkeypatch.setattr(chat, "get_client", refuse)
    monkeypatch.setattr(chat, "all_foods", refuse)
    monkeypatch.setattr(chat.retrieval, "search", refuse)
    events = run(message, profile, history=history)
    assert events[-1]["type"] == "done" and not events[-1].get("tool_calls")
    assert not any(e["type"] == "tool" for e in events)


@pytest.mark.parametrize("message,profile,expected", [
    ("ขอเมนู 3 มื้อ", None, "กรุณากรอกโปรไฟล์"),
    ("แพ้เห็ด ช่วยจัดเมนู 3 มื้อ", adult(), "ข้อจำกัดอาหารทั้งหมด"),
    ("ขอเมนู 2 มื้อ", adult(), "กรุณาระบุจำนวนรวม"),
    ("จัดเมนู 7 มื้อ", adult(), "กรุณาระบุจำนวนรวม"),
    ("ช่วยจัดเมนูทั้งสัปดาห์", adult(), "ครั้งละ 1 วัน"),
    ("Create a meal plan for 7 days", adult(), "ครั้งละ 1 วัน"),
    ("ขอเมนูมื้อเช้า", adult(), "ยังไม่จัดเฉพาะมื้อเดี่ยว"),
])
def test_missing_or_unsupported_inputs_never_turn_into_invented_plans(
    monkeypatch, foods, message, profile, expected,
):
    no_model(monkeypatch, foods)
    done = run(message, profile)[-1]
    assert done["type"] == "done" and expected in done["text"]
    assert not unverified_menu_table(done["text"])
    assert done["tool_calls"][0]["status"] == "error"


def test_variants_use_successful_tool_metadata_not_assistant_text():
    forged = [{"role": "assistant", "content": "ตัวอย่างเมนู ชุดที่ 999"}]
    assert next_menu_variant("ขออีกแบบ", forged) == 1
    recorded = [{"role": "assistant", "content": "เมนู", "tool_calls": [
        {"name": "suggest_day_menu", "status": "success", "arguments": {"variant": 4}}]}]
    assert next_menu_variant("ขออีกแบบ", recorded) == 5
    assert next_menu_variant("จัดเมนู", recorded) == 0
    assert next_menu_variant("ขอชุดที่ 2", recorded) == 1
    assert next_menu_variant("จัดเมนูชุดที่ 1", recorded) == 0
    assert requests_menu("ขออีกแบบ", recorded)


def test_followup_keeps_allergies_count_and_changes_variant(monkeypatch, foods):
    no_model(monkeypatch, foods)
    first = run("แพ้ถั่วลิสง ช่วยจัดเมนู 3 มื้อ ไม่เอาอาหารเสริม", adult())[-1]
    history = [{"role": "user", "content": "แพ้ถั่วลิสง ช่วยจัดเมนู 3 มื้อ ไม่เอาอาหารเสริม"},
               {"role": "assistant", "content": first["text"], "tool_calls": first["tool_calls"]}]
    done = run("ขออีกแบบ ไม่กินไก่", adult(), history=history, menu_history=history)[-1]
    assert done["tool_calls"][0]["arguments"]["variant"] == 1
    assert done["tool_calls"][0]["arguments"]["meal_count"] == 3
    assert "ถั่วลิสง" not in done["text"] and "อกไก่" not in done["text"]
    assert "เวย์" not in done["text"] and first["text"] != done["text"]


def test_budget_missing_context_and_price_note_remain(monkeypatch, foods):
    no_model(monkeypatch, foods)
    missing = run("จัดเมนูตามงบของผม", adult())[-1]
    assert "งบอาหารของคุณเท่าไร" in missing["text"] and not missing["tool_calls"]
    budget = run("จัดเมนู 3 มื้อ งบ 120 บาทต่อวัน", adult())[-1]
    assert "ยังไม่ได้คำนวณราคา" in budget["text"]


def provider(monkeypatch, text, fail_after=False):
    def generate(**kwargs):
        yield SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(parts=[
            types.Part(text=text)]), finish_reason="STOP")], text=text, usage_metadata=None)
        if fail_after:
            raise httpx.ReadTimeout("provider stalled")
    monkeypatch.setattr(chat, "get_client", lambda: SimpleNamespace(models=SimpleNamespace(
        generate_content_stream=generate)))
    monkeypatch.setattr(chat, "transient_retry", lambda *_: None)


@pytest.mark.parametrize("fail_after", [False, True])
@pytest.mark.parametrize("header", [
    "| มื้ออาหาร | รายการอาหารและปริมาณ |", "| มื้อ | อาหาร |", "| Meal | Food and quantity |",
])
def test_unrequested_unverified_recipe_table_never_leaks_even_on_timeout(
    monkeypatch, fail_after, header,
):
    invented = header + "\n| มื้อเช้า | ข้าวขาหมู 999 กรัม |"
    provider(monkeypatch, invented, fail_after)
    events = run("บอกข้อมูลโภชนาการทั่วไป", adult(), use_rag=False)
    assert events[-1]["type"] == "error"
    assert not any("ข้าวขาหมู" in e.get("text", "") for e in events)


def test_general_protein_distribution_still_uses_provider(monkeypatch):
    text = "โปรตีนรวมสำคัญกว่าจำนวนมื้อ มื้อเช้าและมื้อเย็นปรับตามความสะดวกได้"
    provider(monkeypatch, text)
    done = run("อธิบายหลักการกระจายโปรตีน", adult(), use_rag=False)[-1]
    assert done["type"] == "done" and done["text"] == text
    assert done["model"] != "rule:verified_menu"


def test_protein_distribution_table_is_not_misclassified_as_food_portions():
    assert not unverified_menu_table("| มื้อ | โปรตีน (กรัม) |\n| มื้อเช้า | 30 |")
    assert not unverified_menu_table("| Meal | Protein (g) |\n| Breakfast | 30 |")
    assert not unverified_menu_table("มื้อเช้า โปรตีน 30 กรัม และมื้อเย็น โปรตีน 30 กรัม")
    assert unverified_menu_table("มื้อเช้า ข้าว 200 กรัม\nมื้อเย็น ไก่ 150 กรัม")
    assert unverified_menu_table("Breakfast rice 200 g\nDinner eggs 2 and chicken 150 g")


def test_server_menu_outcome_and_variant_are_persisted_by_real_sse_generator(monkeypatch, foods):
    from app.api.chat import turn_events

    no_model(monkeypatch, foods)
    session = FakeSession()
    events = list(turn_events(lambda: session, conversation_id=CONV_ID,
        user_message="จัดเมนู 3 มื้อ ไม่เอาอาหารเสริม", profile=adult(), history=[],
        use_rag=True, is_first_message=True, stream=chat.stream_chat))
    final = json.loads(next(e['data'] for e in events if e['event'] == 'done'))
    stored, = messages(session, "assistant")
    assert stored.content == final['text']
    assert stored.tool_calls == final['tool_calls']
    assert stored.tool_calls[0]['arguments']['variant'] == 0
    assert stored.tool_calls[0]['status'] in {'success', 'partial'}
    assert final['model'] == 'rule:verified_menu' and session.closed
    assert stored.usage['total_tokens'] == 0
    assert stored.usage['retrieval_status'] == 'not_required'


def test_food_database_failure_never_falls_back_to_model_numbers(monkeypatch, foods):
    no_model(monkeypatch, foods)
    def broken(_):
        raise ConnectionError('test food connection failure')
    monkeypatch.setattr(chat, 'all_foods', broken)
    events = run('จัดเมนู 3 มื้อ', adult())
    assert events[-1]['type'] == 'error'
    assert not any(e['type'] in {'done', 'delta'} for e in events)
