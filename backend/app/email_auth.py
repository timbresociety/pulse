"""Passwordless email challenge creation and delivery."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import EmailLoginChallenge

log = logging.getLogger("pulse.email_auth")


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def _digest(email: str, value: str) -> str:
    # A database leak must not turn a code or magic-link token into a usable
    # credential. The server secret also prevents offline guessing of codes.
    message = f"{settings.jwt_secret}|{email}|{value}".encode()
    return hashlib.sha256(message).hexdigest()


def _magic_digest(value: str) -> str:
    return hashlib.sha256(f"{settings.jwt_secret}|magic|{value}".encode()).hexdigest()


async def issue_email_challenge(
    db: AsyncSession, email: str
) -> tuple[EmailLoginChallenge, str, str]:
    normalized = normalize_email(email)
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=settings.email_login_ttl_minutes)
    recent_count = await db.scalar(
        select(func.count())
        .select_from(EmailLoginChallenge)
        .where(
            EmailLoginChallenge.email == normalized,
            EmailLoginChallenge.created_at >= window_start,
        )
    )
    if (recent_count or 0) >= settings.email_login_max_requests_per_window:
        raise HTTPException(429, "Too many sign-in emails. Please try again shortly.")

    # A new request supersedes older credentials for the same address.
    active = await db.execute(
        select(EmailLoginChallenge)
        .where(
            EmailLoginChallenge.email == normalized,
            EmailLoginChallenge.consumed_at.is_(None),
            EmailLoginChallenge.expires_at > now,
        )
        .with_for_update()
    )
    for prior in active.scalars():
        prior.consumed_at = now

    code = f"{secrets.randbelow(1_000_000):06d}"
    magic_token = secrets.token_urlsafe(32)
    challenge = EmailLoginChallenge(
        email=normalized,
        code_hash=_digest(normalized, code),
        magic_token_hash=_magic_digest(magic_token),
        expires_at=now + timedelta(minutes=settings.email_login_ttl_minutes),
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    return challenge, code, magic_token


async def deliver_email_challenge(*, email: str, code: str, magic_token: str) -> None:
    if not settings.email_delivery_ready:
        raise HTTPException(503, "Email sign-in is not configured yet.")

    magic_url = f"{settings.public_api_url.rstrip('/')}/auth/email/magic?token={magic_token}"
    subject = "Your Pulse sign-in code"
    text_body = (
        f"Your Pulse code is {code}. It expires in {settings.email_login_ttl_minutes} minutes.\n\n"
        f"Or sign in instantly: {magic_url}\n\n"
        "If you did not request this, you can ignore this email."
    )

    if settings.email_delivery == "console":
        if not settings.debug:
            raise HTTPException(503, "Console email delivery is only available in development.")
        log.warning("Local sign-in email for %s:\n%s", email, text_body)
        return

    if settings.email_delivery != "resend":
        raise HTTPException(503, "Unsupported email delivery provider.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [email],
                "subject": subject,
                "text": text_body,
            },
        )
    if response.is_error:
        log.warning("Email delivery failed: %s", response.status_code)
        raise HTTPException(503, "We could not send that sign-in email. Please try again.")


async def consume_email_code(db: AsyncSession, *, email: str, code: str) -> str:
    normalized = normalize_email(email)
    now = datetime.now(timezone.utc)
    challenge = await db.scalar(
        select(EmailLoginChallenge)
        .where(
            EmailLoginChallenge.email == normalized,
            EmailLoginChallenge.code_hash == _digest(normalized, code.strip()),
        )
        .order_by(EmailLoginChallenge.created_at.desc())
        .with_for_update()
    )
    if challenge is None or challenge.consumed_at is not None or challenge.expires_at <= now:
        raise HTTPException(400, "That sign-in code is invalid or has expired.")
    challenge.consumed_at = now
    return normalized


async def consume_magic_token(db: AsyncSession, *, magic_token: str) -> str:
    now = datetime.now(timezone.utc)
    challenge = await db.scalar(
        select(EmailLoginChallenge)
        .where(EmailLoginChallenge.magic_token_hash == _magic_digest(magic_token))
        .with_for_update()
    )
    if challenge is None or challenge.consumed_at is not None or challenge.expires_at <= now:
        raise HTTPException(400, "That sign-in link is invalid or has expired.")
    challenge.consumed_at = now
    return challenge.email
