"""The chat bubble must never carry the provider's error payload.

A 429 used to interpolate Google's whole JSON into the message - quota metric
names, the model id, rpc type urls, all English inside a Thai UI. Found by
driving the real web UI on 2026-09-04; the screenshot is why this file exists.
"""

import pytest

from app.services.chat import user_facing_error

RAW_429 = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
    "current quota, please check your plan and billing details. For more information "
    "on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. "
    "* Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 500, model: gemini-3.5-flash-lite'}}"
)

#: Anything here appearing in an answer means the payload got through.
LEAKS = (
    "googleapis", "google.dev", "quota exceeded for metric", "gemini-3.5",
    "resource_exhausted", "@type", "billing", "http",
)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (RuntimeError(RAW_429), "โควตา"),
        (TimeoutError("504 DEADLINE_EXCEEDED"), "นานเกินไป"),
        (RuntimeError("401 UNAUTHENTICATED: API key not valid"), "ผู้ดูแลระบบ"),
        (RuntimeError("503 UNAVAILABLE: model overloaded"), "ขัดข้องชั่วคราว"),
    ],
)
def test_known_failures_get_an_actionable_thai_message(exc, expected):
    assert expected in user_facing_error(exc)


@pytest.mark.parametrize(
    "exc",
    [RuntimeError(RAW_429), ValueError("something odd"), TimeoutError("504 DEADLINE_EXCEEDED")],
)
def test_no_provider_detail_ever_reaches_the_user(exc):
    message = user_facing_error(exc).lower()
    for leak in LEAKS:
        assert leak not in message, f"{leak!r} leaked into: {message}"


def test_unknown_failure_still_gets_a_thai_sentence():
    message = user_facing_error(ValueError("kaboom"))
    assert "kaboom" not in message
    assert message.strip().endswith("แจ้งผู้ดูแลระบบ")
