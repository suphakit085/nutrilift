"""Account email over Resend HTTPS or SMTP, with no secrets in logs/responses."""

import hashlib
import logging
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


def require_email_delivery() -> None:
    if not settings.email_delivery_configured:
        raise HTTPException(503, "ระบบส่งอีเมลยังไม่พร้อม กรุณาติดต่อผู้ดูแลระบบ")


def action_url(purpose: str, token: str) -> str:
    page = {
        "verify_email": "verify-email",
        "reset_password": "reset-password",
        "change_email": "confirm-email",
    }[purpose]
    # Fragments are not sent to web servers or included in HTTP Referer headers.
    return f"{settings.frontend_url.rstrip('/')}/{page}#token={quote(token, safe='')}"


def send_action_email(email: str, purpose: str, token: str) -> None:
    require_email_delivery()
    subject = {
        "verify_email": "ยืนยันอีเมล NutriLift",
        "reset_password": "ตั้งรหัสผ่าน NutriLift ใหม่",
        "change_email": "ยืนยันอีเมลใหม่ของ NutriLift",
    }[purpose]
    minutes = (
        settings.password_reset_expire_minutes
        if purpose == "reset_password"
        else settings.email_verification_expire_minutes
    )
    sender = str(Address("NutriLift", addr_spec=settings.email_sender))
    recipient = str(Address(addr_spec=email))
    body = (
        f"{subject}\n\nเปิดลิงก์นี้เพื่อดำเนินการ:\n{action_url(purpose, token)}\n\n"
        f"ลิงก์ใช้ได้ครั้งเดียว ภายใน {minutes} นาที\n"
        "หากคุณไม่ได้ร้องขอรายการนี้ ไม่ต้องเปิดลิงก์และไม่ต้องดำเนินการใด ๆ\n"
        "NutriLift จะไม่ขอให้คุณส่งรหัสผ่านกลับทางอีเมล"
    )
    if settings.email_provider == "resend":
        # Same action retried twice gets one provider message, without exposing
        # the raw link token or recipient in the header. No silent SMTP fallback.
        digest = hashlib.sha256(f"{purpose}:{email}:{token}".encode()).hexdigest()
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            response = client.post(
                "https://api.resend.com/emails",
                headers={
                    "User-Agent": "NutriLift/0.1",
                    "Authorization": f"Bearer {settings.resend_api_key.get_secret_value().strip()}",
                    "Idempotency-Key": f"account-{digest}",
                },
                json={"from": sender, "to": [recipient], "subject": subject, "text": body},
            )
            if not response.is_success:
                # Provider errors may contain recipients/content; don't expose them.
                raise RuntimeError(
                    f"Account email provider rejected request ({response.status_code})"
                )
            result = response.json()
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("id"), str)
                or not result["id"]
            ):
                raise RuntimeError("Account email provider did not acknowledge the message")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    context = ssl.create_default_context()
    if settings.smtp_ssl:
        connection = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=10, context=context
        )
    else:
        connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    with connection as smtp:
        if settings.smtp_starttls and not settings.smtp_ssl:
            smtp.starttls(context=context)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


def deliver_action_email(email: str, purpose: str, token: str) -> None:
    """Background work keeps account recovery responses independent of mailbox existence."""
    try:
        send_action_email(email, purpose, token)
    except Exception:
        # Provider errors can include addresses; never log the message/link/token.
        logger.error("Account email delivery failed; check mail service configuration and retry")
