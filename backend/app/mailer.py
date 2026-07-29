import asyncio
import smtplib
from email.message import EmailMessage

import httpx

from app.config import settings


class EmailDeliveryError(RuntimeError):
    pass


def _message(recipient: str, code: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"{code} is your Pulse sign-in code"
    message["From"] = settings.otp_from_email
    message["To"] = recipient
    message.set_content(
        "Use this one-time code to sign in to Pulse:\n\n"
        f"{code}\n\n"
        f"It expires in {settings.otp_expire_minutes} minutes. "
        "If you did not request this code, you can ignore this email."
    )
    return message


async def _send_with_resend(recipient: str, code: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.otp_from_email,
                "to": [recipient],
                "subject": f"{code} is your Pulse sign-in code",
                "text": _message(recipient, code).get_content(),
            },
        )
    if response.status_code >= 300:
        raise EmailDeliveryError(f"Email provider returned HTTP {response.status_code}")


def _send_with_smtp(recipient: str, code: str) -> None:
    message = _message(recipient, code)
    smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
    with smtp_class(settings.smtp_host, settings.smtp_port, timeout=10) as client:
        if settings.smtp_starttls and not settings.smtp_use_ssl:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


async def send_otp_email(recipient: str, code: str) -> None:
    try:
        if settings.resend_api_key:
            await _send_with_resend(recipient, code)
            return
        if settings.smtp_host:
            await asyncio.to_thread(_send_with_smtp, recipient, code)
            return
    except (httpx.HTTPError, OSError, smtplib.SMTPException, EmailDeliveryError) as error:
        raise EmailDeliveryError("Unable to send sign-in email") from error

    if not settings.debug:
        raise EmailDeliveryError("Email delivery is not configured")
