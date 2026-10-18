"""HTTP/SMTP delivery contracts and secret-free failures; no external email."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.core.config import settings
from app.services import account_email


@pytest.fixture(autouse=True)
def isolate_mail_configuration(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "email_from", "")


@pytest.fixture
def resend_transport(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "email_from", "accounts@example.com")
    monkeypatch.setattr(settings, "resend_api_key", SecretStr("re_test_only_secret"))
    monkeypatch.setattr(settings, "frontend_url", "https://example.com")
    requests = []
    result = {"status": 200, "json": {"id": "test-message-id"}}
    original_client = httpx.Client

    def handle(request):
        requests.append(request)
        if "error" in result:
            raise result["error"]
        return httpx.Response(result["status"], json=result["json"])

    def client(**kwargs):
        return original_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(account_email.httpx, "Client", client)
    smtp = MagicMock(side_effect=AssertionError("Resend must never fall back to SMTP"))
    monkeypatch.setattr(account_email.smtplib, "SMTP", smtp)
    monkeypatch.setattr(account_email.smtplib, "SMTP_SSL", smtp)
    return SimpleNamespace(requests=requests, result=result, smtp=smtp)


@pytest.mark.parametrize(
    "purpose,page",
    [
        ("verify_email", "verify-email"),
        ("reset_password", "reset-password"),
        ("change_email", "confirm-email"),
    ],
)
def test_resend_delivers_account_links_as_authenticated_https(resend_transport, purpose, page):
    account_email.send_action_email("owner@example.com", purpose, "opaque-token")
    (request,) = resend_transport.requests
    assert request.method == "POST" and str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_test_only_secret"
    assert request.headers["user-agent"] == "NutriLift/0.1"
    payload = json.loads(request.content)
    assert payload["from"] == "NutriLift <accounts@example.com>"
    assert payload["to"] == ["owner@example.com"]
    assert f"https://example.com/{page}#token=opaque-token" in payload["text"]
    assert "re_test_only_secret" not in request.content.decode()
    assert "opaque-token" not in request.headers["idempotency-key"]
    resend_transport.smtp.assert_not_called()


def test_resend_repeated_action_is_idempotent_but_new_links_get_new_keys(resend_transport):
    for token in ["first-link", "first-link", "replacement-link"]:
        account_email.send_action_email("owner@example.com", "verify_email", token)
    keys = [request.headers["idempotency-key"] for request in resend_transport.requests]
    assert keys[0] == keys[1] and keys[1] != keys[2]


@pytest.mark.parametrize("status", [302, 401, 403, 429, 503])
def test_resend_rejection_is_not_treated_as_success_or_logged_with_secrets(
    resend_transport, status, caplog
):
    resend_transport.result.update(
        status=status,
        json={
            "message": "owner@example.com opaque-token re_test_only_secret",
        },
    )
    with pytest.raises(RuntimeError, match=f"rejected request \\({status}\\)"):
        account_email.send_action_email("owner@example.com", "reset_password", "opaque-token")
    account_email.deliver_action_email("owner@example.com", "reset_password", "opaque-token")
    assert "delivery failed" in caplog.text
    for secret in ("owner@example.com", "opaque-token", "re_test_only_secret"):
        assert secret not in caplog.text
    resend_transport.smtp.assert_not_called()


def test_resend_timeout_does_not_log_sensitive_provider_exception(resend_transport, caplog):
    resend_transport.result["error"] = httpx.ReadTimeout("owner@example.com opaque-token")
    account_email.deliver_action_email("owner@example.com", "verify_email", "opaque-token")
    assert "delivery failed" in caplog.text
    assert "owner@example.com" not in caplog.text and "opaque-token" not in caplog.text


@pytest.mark.parametrize("body", [{}, {"id": ""}, {"id": None}, []])
def test_resend_requires_provider_acknowledgement(resend_transport, body):
    resend_transport.result["json"] = body
    with pytest.raises(RuntimeError, match="did not acknowledge"):
        account_email.send_action_email("owner@example.com", "verify_email", "opaque-token")


def test_resend_missing_credentials_stops_before_any_outbound_request(
    resend_transport, monkeypatch
):
    monkeypatch.setattr(settings, "resend_api_key", SecretStr(""))
    with pytest.raises(HTTPException) as caught:
        account_email.send_action_email("owner@example.com", "verify_email", "opaque-token")
    assert caught.value.status_code == 503
    assert resend_transport.requests == []


def test_smtp_uses_tls_login_and_fragment_links(monkeypatch):
    smtp = MagicMock()
    factory = MagicMock(return_value=smtp)
    monkeypatch.setattr(account_email.smtplib, "SMTP", factory)
    for key, value in {
        "smtp_host": "smtp.example.com",
        "smtp_from_email": "accounts@example.com",
        "smtp_username": "mailer",
        "smtp_password": SecretStr("test-only-secret"),
        "smtp_starttls": True,
        "smtp_ssl": False,
        "frontend_url": "https://example.com/",
    }.items():
        monkeypatch.setattr(settings, key, value)
    account_email.send_action_email("owner@example.com", "reset_password", "opaque-token")
    connection = smtp.__enter__.return_value
    connection.starttls.assert_called_once()
    connection.login.assert_called_once_with("mailer", "test-only-secret")
    message = connection.send_message.call_args.args[0]
    assert "https://example.com/reset-password#token=opaque-token" in message.get_content()
    assert str(message["To"]) == "owner@example.com"
    assert "test-only-secret" not in message.as_string()


def test_failed_delivery_never_logs_token_address_or_provider_error(monkeypatch, caplog):
    def failing(*_):
        raise RuntimeError("owner@example.com opaque-token provider-secret")

    monkeypatch.setattr(account_email, "send_action_email", failing)
    account_email.deliver_action_email("owner@example.com", "verify_email", "opaque-token")
    assert "delivery failed" in caplog.text
    for sensitive in ("owner@example.com", "opaque-token", "provider-secret"):
        assert sensitive not in caplog.text
