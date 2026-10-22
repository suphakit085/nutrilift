"""Weight/height typed in chat without a saved profile get the profile screening."""

from types import SimpleNamespace

import pytest

from app.services import chat, guardrails
from tests.test_functional_prompt_fixes import client_for, ledger, understood

Flag = guardrails.Flag


@pytest.mark.parametrize(
    ("weight", "height", "goal", "expected"),
    [
        (199.9, None, None, []),
        (200, None, "bulk", [Flag.SPECIALIST_PROFILE]),
        (300, 180, "bulk", [Flag.SPECIALIST_PROFILE, Flag.BULK_REVIEW]),
        (38, 170, "cut", [Flag.SPECIALIST_PROFILE, Flag.UNDERWEIGHT]),  # BMI 13.1
        (52, 178, "cut", [Flag.UNDERWEIGHT]),  # BMI 16.4
        (91.875, 175, "bulk", [Flag.BULK_REVIEW]),  # BMI 30.0
        (91.8, 175, "bulk", []),  # BMI 29.98
        (110, 175, "cut", []),  # BMI 35.9 without a bulk goal
        (70, 175, "bulk", []),
        (None, 170, "cut", []),
    ],
)
def test_stated_measurement_boundaries_match_the_profile_policy(weight, height, goal, expected):
    assert guardrails.check_stated_measurements(weight, height, goal).flags == expected


def stated(task, weight, height, goal):
    measurements = {}
    message = ""
    if weight is not None:
        measurements["weight_kg"] = {"value": weight, "user_turn": 0, "quote": f"{weight:g} กก."}
        message += f"น้ำหนัก {weight:g} กก. "
    if height is not None:
        measurements["height_cm"] = {"value": height, "user_turn": 0, "quote": f"สูง {height:g}"}
        message += f"สูง {height:g} "
    goal_words = {"cut": "ลดไขมัน", "bulk": "เพิ่มกล้าม"}[goal]
    message += f"อยาก{goal_words} ควรกินยังไง"
    state = understood(
        task=task,
        personal_context=True,
        goal=goal,
        goal_quote=goal_words,
        goal_user_turn=0,
        **measurements,
    )
    return state, message


def run(monkeypatch, state, message, *answers):
    client, calls = client_for(state.model_dump_json(), *answers)
    monkeypatch.setattr(chat, "get_client", lambda: client)
    monkeypatch.setattr(chat.retrieval, "search", lambda *_, **__: [])
    result = chat.collect_understood_answer(
        SimpleNamespace(commit=lambda: None), user_message=message, profile=None
    )
    return result, calls


@pytest.mark.parametrize("task", ["knowledge", "calculate_targets", "plan_menu"])
@pytest.mark.parametrize(("weight", "height", "goal"), [(38, 170, "cut"), (250, None, "bulk")])
def test_out_of_range_stated_values_stop_before_any_answer_generation(
    monkeypatch, task, weight, height, goal
):
    state, message = stated(task, weight, height, goal)
    result, calls = run(monkeypatch, state, message, "ลดพลังงานลง 500 kcal ต่อวัน")
    assert result["type"] == "done" and result["model"] == "rule:specialist_profile"
    assert "500" not in result["text"] and "แพทย์หรือนักกำหนดอาหาร" in result["text"]
    # 250 kg is already refused by the text guard before interpretation; the
    # BMI case needs the interpreted values. Neither generates an answer.
    assert len(calls) <= 1
    assert "specialist_profile" in result["safety_flags"]


@pytest.mark.parametrize(
    ("weight", "height", "goal", "instruction"),
    [(52, 178, "cut", "BMI ต่ำกว่า 18.5"), (110, 175, "bulk", "BMI ตั้งแต่ 30")],
)
def test_in_range_risky_values_constrain_the_generated_answer(
    monkeypatch, weight, height, goal, instruction
):
    state, message = stated("knowledge", weight, height, goal)
    result, calls = run(monkeypatch, state, message, "กินให้พอและปรึกษาผู้เชี่ยวชาญ", ledger("advice"))
    assert result["type"] == "done"
    assert instruction in calls[1]["config"].system_instruction


def test_normal_stated_values_add_no_screening(monkeypatch):
    state, message = stated("knowledge", 70, 175, "bulk")
    result, calls = run(monkeypatch, state, message, "ฝึกและกินโปรตีนให้พอ", ledger("advice"))
    assert result["type"] == "done" and result["safety_flags"] == []
    system = calls[1]["config"].system_instruction
    assert "BMI ต่ำกว่า 18.5" not in system and "BMI ตั้งแต่ 30" not in system
