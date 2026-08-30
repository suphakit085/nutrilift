"""Tests for citation filtering.

The answer shown to the user must only credit passages it actually referenced.
Attaching every retrieved passage would display misleading sources and inflate
the groundedness score in the evaluation.
"""

from app.services.chat import cited_only

PASSAGES = [
    {"label": "S1", "title": "โปรตีน", "document_slug": "protein-requirement"},
    {"label": "S2", "title": "พลังงาน", "document_slug": "energy-balance-cut-bulk"},
    {"label": "S3", "title": "ครีเอทีน", "document_slug": "creatine"},
]


def labels(result):
    return [c["label"] for c in result]


def test_keeps_only_referenced_passages():
    answer = "ควรกินโปรตีน 1.6-2.2 g/kg [S1] และคุมพลังงานตามเป้า [S3]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1", "S3"]


def test_returns_empty_when_answer_cites_nothing():
    answer = "ข้าวมันไก่ 1 จานมีประมาณ 596 กิโลแคลอรี่ โปรตีน 26 กรัม"
    assert cited_only(answer, PASSAGES) == []


def test_preserves_retrieval_order_not_mention_order():
    answer = "อ้างอิงหลัง [S3] แล้วค่อยอ้างอิงแรก [S1]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1", "S3"]


def test_ignores_invented_labels():
    """The model sometimes writes a marker for a passage that was never sent."""
    answer = "ตามงานวิจัย [S9] และ [S1]"
    assert labels(cited_only(answer, PASSAGES)) == ["S1"]


def test_deduplicates_repeated_markers():
    answer = "[S1] ย่อหน้าแรก ... [S1] ย่อหน้าสอง ... [S1] สรุป"
    assert labels(cited_only(answer, PASSAGES)) == ["S1"]


def test_tolerates_spacing_inside_brackets():
    assert labels(cited_only("ข้อความ [ S2 ]", PASSAGES)) == ["S2"]


def test_lowercase_marker_still_matches():
    assert labels(cited_only("ข้อความ [s2]", PASSAGES)) == ["S2"]


def test_no_passages_returns_empty():
    assert cited_only("อะไรก็ตาม [S1]", []) == []


def test_empty_answer_returns_empty():
    assert cited_only("", PASSAGES) == []


def test_does_not_match_other_bracketed_text():
    """Markdown links and bracketed notes must not be read as citations."""
    answer = "ดูเพิ่มเติม [ฐานข้อมูลอาหาร] และ [S2]"
    assert labels(cited_only(answer, PASSAGES)) == ["S2"]
