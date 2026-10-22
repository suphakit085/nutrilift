from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.services import chat, guardrails, prompts
from app.services.calculation_methods import methods_note, target_methods_note
from app.services.nutrition import NutritionInputError, ProfileInput, calc_nutrition_targets


def adult(**changes):
    return replace(ProfileInput(sex="male", birth_year=2000, height_cm=175, weight_kg=70,
                                activity_level="moderate", goal="maintain"), **changes)


@pytest.mark.parametrize("goal", ["cut", "bulk", "maintain"])
@pytest.mark.parametrize("weight,height", [(200, 230), (300, 230), (160, 200), (50, 180)])
def test_outside_support_cannot_produce_targets_or_menu(goal, weight, height, monkeypatch):
    profile = adult(weight_kg=weight, height_cm=height, goal=goal)
    with pytest.raises(NutritionInputError, match="ปรึกษาแพทย์"):
        calc_nutrition_targets(profile)
    monkeypatch.setattr(chat, "get_client", lambda: pytest.fail("must not call model"))
    monkeypatch.setattr(chat.retrieval, "search", lambda *a, **k: pytest.fail("no retrieval"))
    db = SimpleNamespace(commit=lambda: None, rollback=lambda: None)
    answer = chat.collect_answer(db, user_message="ช่วยจัดเมนู 3 มื้อ", profile=profile)
    assert answer["model"] == "rule:specialist_profile"
    assert not answer["tool_calls"] and "200 กก." in answer["text"]
    assert not guardrails.personalization_allowed(guardrails.check_profile(profile))


@pytest.mark.parametrize("weight,expected", [
    (119.999, "bulk"), (120, "maintain"), (159.999, "maintain"),
])
def test_high_bmi_bulk_has_no_surplus_without_diagnosing(weight, expected):
    profile = adult(weight_kg=weight, height_cm=200, goal="bulk")
    result = calc_nutrition_targets(profile)
    assert result["effective_goal"] == expected
    assert profile.goal == "bulk"
    if expected == "maintain":
        assert result["goal_recommendation"] == "cut"
        assert result["energy_target_kcal"] == result["tdee_kcal"]
        assert result["surplus_suppressed_reason"] == "bmi_screening"
        assert any("ไม่ได้ใช้วินิจฉัย" in warning for warning in result["warnings"])
        assert any("ลดไขมันก่อน bulk" in warning for warning in result["warnings"])
    else:
        assert result["goal_recommendation"] is None


def test_mild_underweight_does_not_cut_but_extreme_is_referred():
    result = calc_nutrition_targets(adult(weight_kg=50, height_cm=175, goal="cut"))
    assert result["effective_goal"] == "maintain"
    assert result["energy_target_kcal"] == result["tdee_kcal"]
    assert calc_nutrition_targets(adult(weight_kg=64, height_cm=200))["bmi"] == 16
    with pytest.raises(NutritionInputError):
        calc_nutrition_targets(adult(weight_kg=63.99, height_cm=200))


@pytest.mark.parametrize("message", [
    "ผมหนัก 200 กก ขอ bulk", "น้ำหนัก 300 kg เพิ่มกล้าม",
    "หนัก ๒๐๐ กิโล ขอ cut", "ผมหนัก 200 โล",
])
def test_declared_extreme_weight_survives_followup(message):
    result = guardrails.check(message)
    assert guardrails.Flag.SPECIALIST_PROFILE in result.flags
    history = guardrails.check_history([{"role": "user", "content": message}])
    assert not guardrails.personalization_allowed(history)
    assert guardrails.safety_reply(history)[0] == "specialist_profile"


def test_ordinary_protein_grams_or_negation_are_not_extreme_weight():
    for message in ["โปรตีน 200 กรัม", "ผมไม่ได้หนัก 200 กก", "ผมหนัก 70 กก"]:
        assert guardrails.Flag.SPECIALIST_PROFILE not in guardrails.check(message).flags


@pytest.mark.parametrize("body_fat,formula", [(None, "Mifflin-St Jeor"), (20, "Katch-McArdle")])
def test_every_computed_value_has_actual_method_and_units(body_fat, formula):
    result = calc_nutrition_targets(adult(body_fat_pct=body_fat))
    methods = {m["key"]: m for m in result["calculation_methods"]}
    assert set(methods) == {"bmr", "tdee", "energy", "protein", "fat", "carb", "bmi"}
    assert methods["bmr"]["name"] == formula
    assert methods["bmr"]["result"] == result["bmr_kcal"]
    assert "1.55" in methods["tdee"]["equation"]
    assert methods["protein"]["result"] == 126
    assert "กติกาโครงการ" in methods["fat"]["basis"]
    assert methods["fat"]["source_url"] is None
    assert formula in methods_note(result["calculation_methods"])


def test_original_prompt_keeps_profile_and_guards_in_both_evaluation_modes():
    for use_rag in [True, False]:
        built = prompts.build_system_prompt(
            use_rag=use_rag,
            profile_summary="ผู้ใช้ยืนยันน้ำหนัก 70 กก.",
            targets_summary="พลังงานจากเครื่องมือ 2277 kcal",
            guard_instructions="ข้อจำกัดความปลอดภัยของคำถามปัจจุบัน",
            passages=[{"label": "S1", "title": "หลักฐานทดสอบ", "content": "เนื้อหาทดสอบ"}],
        )
        assert "กรอบคำตอบที่ต้องปฏิบัติ:" not in built
        assert prompts.BASE_SYSTEM_PROMPT.strip() in built
        assert "ผู้ใช้ยืนยันน้ำหนัก 70 กก." in built
        assert "พลังงานจากเครื่องมือ 2277 kcal" in built
        assert "ข้อจำกัดความปลอดภัยของคำถามปัจจุบัน" in built
        assert ("[S1] หลักฐานทดสอบ" in built) == use_rag
    assert prompts.PROMPT_VERSION == "v1.20.2"


@pytest.mark.parametrize("message", ["ผม BMI 40 ขอ bulk", "BMI: 15.9 จัดเมนูให้หน่อย"])
def test_declared_bmi_is_screened_even_without_saved_measurements(message):
    assert guardrails.Flag.SPECIALIST_PROFILE in guardrails.check(message).flags


def test_protein_only_answer_also_displays_its_calculation_method():
    targets = calc_nutrition_targets(adult())
    assert "70 \u00d7 1.8" in target_methods_note("เป้าโปรตีน 126 กรัมต่อวัน", targets)
    assert "Katch" not in target_methods_note("เป้าโปรตีน 126 กรัมต่อวัน", targets)
    assert "Mifflin" not in target_methods_note("เป้าโปรตีน 126 กรัมต่อวัน", targets)
    assert not target_methods_note("โปรตีนมีความสำคัญต่อกล้ามเนื้อ", targets)
    assert not target_methods_note("โปรตีน 1260 กรัม", targets)


@pytest.mark.parametrize("goal", ["maintain", "bulk"])
def test_high_bmi_recommends_user_select_cut_without_changing_saved_goal(goal):
    p = adult(weight_kg=120, height_cm=200, goal=goal)
    result = calc_nutrition_targets(p)
    assert result["goal_recommendation"] == "cut"
    assert p.goal == goal and result["inputs"]["goal"] == goal
    assert result["effective_goal"] == "maintain"
    assert calc_nutrition_targets(replace(p, goal="cut"))["goal_recommendation"] is None
