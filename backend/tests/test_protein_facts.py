from app.services.protein_facts import explicit_single_meal_absorption_reply


def test_large_single_meal_absorption_question_gets_conservative_answer():
    answer = explicit_single_meal_absorption_reply(
        "ถ้ากินโปรตีน 100 กรัมในมื้อเดียว ร่างกายดูดซึมครบทุกกรัมไหม"
    )
    assert answer is not None
    assert "ระบุเป็นตัวเลขแน่นอน" in answer
    assert "ช่วงห่างตายตัว" in answer


def test_unrelated_protein_question_is_not_intercepted():
    assert explicit_single_meal_absorption_reply("โปรตีนวันละเท่าไร") is None


def test_small_meal_digestion_question_is_not_intercepted():
    assert explicit_single_meal_absorption_reply("โปรตีน 25 กรัมย่อยนานไหม") is None
