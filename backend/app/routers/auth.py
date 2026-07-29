import hmac
from datetime import datetime, timedelta, timezone

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_session_token, generate_otp_code, hash_otp, upsert_user
from app.config import settings
from app.database import get_db
from app.mailer import EmailDeliveryError, send_otp_email
from app.models import EmailOtpChallenge
from app.schemas import (
    AuthMethodsOut,
    EmailLoginIn,
    EmailLoginOut,
    EmailOtpRequestOut,
    EmailOtpVerifyIn,
    TokenOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()
if settings.google_enabled:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


@router.get("/methods", response_model=AuthMethodsOut)
async def auth_methods():
    return AuthMethodsOut(
        email_otp=settings.otp_available,
        email_login=settings.email_login_enabled,
        google=settings.google_enabled,
    )


@router.get("/google/login")
async def google_login(request: Request):
    if not settings.google_enabled:
        raise HTTPException(503, "Google OAuth not configured. Use /api/auth/dev-login in DEBUG mode.")
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.google_enabled:
        raise HTTPException(503, "Google OAuth not configured.")
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo") or {}
    email = info.get("email")
    if not email:
        raise HTTPException(400, "Google did not return an email")
    user = await upsert_user(
        db,
        email=email,
        google_sub=info.get("sub"),
        display_name=info.get("name"),
        avatar_url=info.get("picture"),
    )
    session_token = create_session_token(user.id)
    # Hand the token to the PWA via URL fragment
    return RedirectResponse(f"{settings.frontend_url}/#token={session_token}")


@router.post("/email-login", response_model=EmailLoginOut)
async def email_login(payload: EmailLoginIn, db: AsyncSession = Depends(get_db)):
    """Passwordless, unverified sign-in for sharing this prototype with testers."""
    if not settings.email_login_enabled:
        raise HTTPException(404, "Not found")
    user = await upsert_user(db, email=payload.email)
    return EmailLoginOut(access_token=create_session_token(user.id), user=user)


@router.post("/email-otp/request", response_model=EmailOtpRequestOut)
async def request_email_otp(payload: EmailLoginIn, db: AsyncSession = Depends(get_db)):
    if not settings.otp_available:
        raise HTTPException(503, "Email code sign-in is not configured")

    now = datetime.now(timezone.utc)
    resend_after = now - timedelta(seconds=settings.otp_resend_seconds)
    recent = await db.scalar(
        select(EmailOtpChallenge.id)
        .where(
            EmailOtpChallenge.email == payload.email,
            EmailOtpChallenge.created_at >= resend_after,
        )
        .limit(1)
    )
    if recent is not None:
        raise HTTPException(
            429,
            "Please wait before requesting another code",
            headers={"Retry-After": str(settings.otp_resend_seconds)},
        )

    # A newly requested code invalidates any older unconsumed codes.
    await db.execute(
        update(EmailOtpChallenge)
        .where(
            EmailOtpChallenge.email == payload.email,
            EmailOtpChallenge.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    challenge = EmailOtpChallenge(
        email=payload.email,
        code_digest="",
        expires_at=now + timedelta(minutes=settings.otp_expire_minutes),
    )
    db.add(challenge)
    await db.flush()

    code = generate_otp_code()
    challenge.code_digest = hash_otp(challenge.id, payload.email, code)
    try:
        await send_otp_email(payload.email, code)
    except EmailDeliveryError as error:
        await db.rollback()
        raise HTTPException(502, "We could not send the sign-in code. Try again shortly.") from error
    await db.commit()

    dev_code = code if settings.debug and not settings.otp_delivery_configured else None
    return EmailOtpRequestOut(
        challenge_id=challenge.id,
        expires_in_seconds=settings.otp_expire_minutes * 60,
        dev_code=dev_code,
    )


@router.post("/email-otp/verify", response_model=EmailLoginOut)
async def verify_email_otp(payload: EmailOtpVerifyIn, db: AsyncSession = Depends(get_db)):
    if not settings.otp_available:
        raise HTTPException(503, "Email code sign-in is not configured")

    now = datetime.now(timezone.utc)
    challenge = (
        await db.execute(
            select(EmailOtpChallenge)
            .where(EmailOtpChallenge.id == payload.challenge_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if challenge is None or challenge.consumed_at is not None:
        raise HTTPException(400, "That code is invalid or expired")
    if challenge.expires_at <= now:
        challenge.consumed_at = now
        await db.commit()
        raise HTTPException(400, "That code is invalid or expired")
    if challenge.attempts >= settings.otp_max_attempts:
        challenge.consumed_at = now
        await db.commit()
        raise HTTPException(429, "Too many attempts. Request a new code.")

    challenge.attempts += 1
    expected = hash_otp(challenge.id, challenge.email, payload.code)
    if not hmac.compare_digest(challenge.code_digest, expected):
        if challenge.attempts >= settings.otp_max_attempts:
            challenge.consumed_at = now
        await db.commit()
        raise HTTPException(400, "That code is invalid or expired")

    challenge.consumed_at = now
    user = await upsert_user(db, email=challenge.email)
    return EmailLoginOut(access_token=create_session_token(user.id), user=user)


@router.post("/dev-login", response_model=TokenOut, include_in_schema=False)
async def dev_login(email: str, db: AsyncSession = Depends(get_db)):
    """Legacy local-testing endpoint. Use /auth/email-login in the frontend."""
    if not settings.debug:
        raise HTTPException(404, "Not found")
    user = await upsert_user(db, email=email)
    return TokenOut(access_token=create_session_token(user.id))
