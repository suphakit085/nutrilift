"""Real SQL lookup: model punctuation loss must not ask for redundant consent."""
import pytest

from app.db.models import Food
from app.services.chat import _run_food_lookup
from tests import test_food_lookup_word_order

db = test_food_lookup_word_order.db

CHICKEN = "อกไก่ไม่มีหนัง, ย่าง"


def lookup(db, message, query="อกไก่ไม่มีหนัง ย่าง"):
    return _run_food_lookup(db, query, user_message=message,
        pending_confirmations=[], partial_candidates_this_turn=[])


def test_canonical_user_name_resolves_model_removed_comma_on_first_turn(db):
    result = lookup(db, f"{CHICKEN} 100 กรัม ขอสารอาหารและที่มา")
    assert result["found"] is True
    assert result["match"] == "exact"
    assert result["results"][0]["name_th"] == CHICKEN


@pytest.mark.parametrize("message", [
    "อกไก่ย่างไม่มีหนัง 100 กรัม", "ช่วยหาอาหารโปรตีนให้หน่อย",
    f"{CHICKEN} กับข้าวสวย 100 กรัม", f"ไม่ใช่ {CHICKEN} เอาอย่างอื่น",
])
def test_ambiguous_multiple_unrelated_or_negated_food_does_not_gain_numbers(db, message):
    result = lookup(db, message)
    assert result["found"] is False
    assert result["results"] == []


def test_short_name_inside_longer_food_is_not_selected(db):
    db.add(Food(name_th="อกไก่ไม่มีหนัง, ย่างพร้อมซอส", serving_desc="100 กรัม",
        serving_g=100, kcal=200, protein_g=10, carb_g=10, fat_g=5,
        source="test:longer"))
    db.commit()
    result = lookup(db, "อกไก่ไม่มีหนัง, ย่างพร้อมซอส 100 กรัม", query="อกไก่ย่างไม่มีหนัง")
    if result["found"]:
        assert result["results"][0]["name_th"] != CHICKEN
    else:
        assert result["results"] == []
