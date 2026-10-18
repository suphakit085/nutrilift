"""Production must refuse to boot on placeholder secrets.

``jwt_secret`` defaults to "change-me" and ``.env.example`` ships an obviously
fake Gemini key. A Render deploy that forgets one env var used to come up
happily - serving tokens anyone could forge. These tests pin the guard without
ever booting the real app in production mode: the check is a pure function of
a Settings object and an environment mapping.
"""

import logging

import pytest

from app.core.config import (
    Settings,
    check_production_settings,
    is_production,
    production_config_problems,
)

GOOD_SECRET = "x" * 40
GOOD_KEY = "real-looking-key-0123456789"
PROD = {"ENVIRONMENT": "production"}
DEV: dict[str, str] = {}


def make_settings(**overrides) -> Settings:
    """A Settings that ignores backend/.env so the test is hermetic."""
    values = {
        "jwt_secret": GOOD_SECRET,
        "gemini_api_key": GOOD_KEY,
        "email_provider": "smtp",
        "email_from": "",
        "smtp_host": "smtp.example.com",
        "smtp_from_email": "accounts@example.com",
        "frontend_url": "https://nutrilift.example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# --- production detection -----------------------------------------------


@pytest.mark.parametrize(
    "environ",
    [
        {"ENVIRONMENT": "production"},
        {"ENVIRONMENT": "Production "},
        {"RENDER": "true"},
        {"RAILWAY_ENVIRONMENT": "production"},
        {"RAILWAY_PROJECT_ID": "abc", "ENVIRONMENT": "development"},
    ],
)
def test_hosting_platform_markers_mean_production(environ):
    """Render/Railway inject these themselves, so forgetting ENVIRONMENT on
    the dashboard must not silently switch the guard off."""
    assert is_production(environ)


@pytest.mark.parametrize("environ", [{}, {"ENVIRONMENT": "development"}, {"RENDERER": "gpu"}])
def test_plain_machines_are_not_production(environ):
    assert not is_production(environ)


# --- findings ------------------------------------------------------------


@pytest.mark.parametrize("secret", ["change-me", "change-me-to-a-long-random-string"])
def test_placeholder_jwt_secret_is_flagged(secret):
    problems = production_config_problems(make_settings(jwt_secret=secret))
    assert any("JWT_SECRET" in p and "placeholder" in p for p in problems)


def test_short_jwt_secret_is_flagged():
    problems = production_config_problems(make_settings(jwt_secret="a" * 31))
    assert any("JWT_SECRET" in p and "31" in p for p in problems)


def test_32_char_secret_passes():
    assert production_config_problems(make_settings(jwt_secret="a" * 32)) == []


@pytest.mark.parametrize("key", ["", "   ", "AIza...", "AIza...xyz"])
def test_missing_or_placeholder_gemini_key_is_flagged(key):
    problems = production_config_problems(make_settings(gemini_api_key=key))
    assert any("GEMINI_API_KEY" in p for p in problems)


def test_every_problem_is_reported_at_once():
    problems = production_config_problems(make_settings(jwt_secret="change-me", gemini_api_key=""))
    assert len(problems) == 2


# --- the guard itself -----------------------------------------------------


def test_production_refuses_to_start_and_names_the_variable():
    with pytest.raises(RuntimeError, match="JWT_SECRET") as excinfo:
        check_production_settings(make_settings(jwt_secret="change-me"), environ=PROD)
    assert "Refusing to start" in str(excinfo.value)


def test_production_refuses_on_empty_gemini_key():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        check_production_settings(make_settings(gemini_api_key=""), environ={"RENDER": "1"})


def test_production_boots_on_good_settings():
    check_production_settings(make_settings(), environ=PROD)


def test_dev_only_warns_so_the_local_checkout_keeps_working(caplog):
    """backend/.env in this repo holds the placeholder secret on purpose."""
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        check_production_settings(make_settings(jwt_secret="change-me"), environ=DEV)
    assert any("INSECURE" in r.message and "JWT_SECRET" in r.message for r in caplog.records)


def test_dev_is_silent_on_good_settings(caplog):
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        check_production_settings(make_settings(), environ=DEV)
    assert not caplog.records


def test_resend_production_config_uses_https_without_smtp_requirements():
    cfg = make_settings(
        email_provider="resend",
        resend_api_key="re_test_only_key",
        email_from="accounts@example.com",
        smtp_host="",
        smtp_from_email="",
        smtp_starttls=False,
        smtp_ssl=False,
    )
    assert cfg.email_delivery_configured
    assert production_config_problems(cfg) == []


@pytest.mark.parametrize(
    "key,sender", [("", "accounts@example.com"), ("   ", "accounts@example.com"), ("re_test", "")]
)
def test_resend_missing_key_or_sender_is_not_ready(key, sender):
    cfg = make_settings(
        email_provider="resend",
        resend_api_key=key,
        email_from=sender,
        smtp_from_email="",
    )
    assert not cfg.email_delivery_configured
    assert any("RESEND_API_KEY" in item for item in production_config_problems(cfg))


def test_resend_api_key_is_redacted_in_settings_repr():
    cfg = make_settings(resend_api_key="re_test_secret_not_for_logs")
    assert "re_test_secret_not_for_logs" not in repr(cfg)


def test_resend_test_sender_cannot_be_mistaken_for_a_production_sender():
    cfg = make_settings(
        email_provider="resend",
        resend_api_key="re_test_only_key",
        email_from="onboarding@resend.dev",
    )
    assert any("verified domain" in item for item in production_config_problems(cfg))


# --- CORS origin normalisation -------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://x.vercel.app/", ["https://x.vercel.app"]),
        ("HTTPS://My-App.Vercel.app//", ["https://my-app.vercel.app"]),
        (
            " http://localhost:3000 , https://x.vercel.app/",
            ["http://localhost:3000", "https://x.vercel.app"],
        ),
        ("http://localhost:3000,,", ["http://localhost:3000"]),
        ("*", ["*"]),
    ],
)
def test_cors_origins_are_normalised(raw, expected):
    """Browsers send ``Origin`` lowercase with no trailing slash and Starlette
    compares strings exactly; a pasted ``https://x.vercel.app/`` never matched."""
    assert make_settings(cors_origins=raw).cors_origin_list == expected
