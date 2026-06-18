from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_session_token, upsert_user
from app.config import settings
from app.database import get_db
from app.schemas import TokenOut

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
        raise HTTPException(503, "Google OAuth not configured. Use /auth/dev-login in DEBUG mode.")
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


@router.post("/dev-login", response_model=TokenOut)
async def dev_login(email: str, db: AsyncSession = Depends(get_db)):
    """Email-only login for local testing. Disabled unless DEBUG=true."""
    if not settings.debug:
        raise HTTPException(404, "Not found")
    user = await upsert_user(db, email=email)
    return TokenOut(access_token=create_session_token(user.id))
