from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_session_token, upsert_user
from app.config import settings
from app.database import get_db
from app.email_auth import (
    consume_email_code,
    consume_magic_token,
    deliver_email_challenge,
    issue_email_challenge,
)
from app.schemas import EmailLoginStartIn, EmailLoginVerifyIn, TokenOut

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


@router.get("/google/login")
async def google_login(request: Request):
    if not settings.google_enabled:
        raise HTTPException(503, "Google OAuth is not configured.")
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


@router.post("/email/start")
async def start_email_login(payload: EmailLoginStartIn, db: AsyncSession = Depends(get_db)):
    """Send both a six-digit code and a one-use magic link to the address."""
    _challenge, code, magic_token = await issue_email_challenge(db, payload.email)
    await deliver_email_challenge(email=payload.email, code=code, magic_token=magic_token)
    return {"status": "sent"}


@router.post("/email/verify", response_model=TokenOut)
async def verify_email_code(payload: EmailLoginVerifyIn, db: AsyncSession = Depends(get_db)):
    email = await consume_email_code(db, email=payload.email, code=payload.code)
    user = await upsert_user(db, email=email)
    return TokenOut(access_token=create_session_token(user.id))


@router.get("/email/magic")
async def verify_magic_link(token: str, db: AsyncSession = Depends(get_db)):
    email = await consume_magic_token(db, magic_token=token)
    user = await upsert_user(db, email=email)
    session_token = create_session_token(user.id)
    return RedirectResponse(f"{settings.frontend_url}/#token={session_token}")


@router.post("/dev-login", response_model=TokenOut)
async def dev_login(email: str, db: AsyncSession = Depends(get_db)):
    """Email-only login for local testing. Disabled unless DEBUG=true."""
    if not settings.debug:
        raise HTTPException(404, "Not found")
    user = await upsert_user(db, email=email)
    return TokenOut(access_token=create_session_token(user.id))
