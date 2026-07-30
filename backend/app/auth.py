import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from app.config import settings
from app.database import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def generate_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(challenge_id: uuid.UUID, email: str, code: str) -> str:
    message = f"{challenge_id}:{email.strip().lower()}:{code}".encode()
    return hmac.new(
        settings.otp_signing_secret.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()


def create_session_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _current_user_id(creds: HTTPAuthorizationCredentials | None) -> uuid.UUID:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing auth token")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid auth token")


def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> uuid.UUID:
    """Authenticate a token when the route's own locked query loads the user."""
    return _current_user_id(creds)


async def _current_user(
    creds: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
    *,
    with_categories: bool,
) -> User:
    category_loading = selectinload(User.categories) if with_categories else noload(User.categories)
    user = await db.scalar(
        select(User)
        .where(User.id == _current_user_id(creds))
        .options(category_loading)
    )
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _current_user(creds, db, with_categories=False)


async def get_current_user_with_categories(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _current_user(creds, db, with_categories=True)


async def upsert_user(
    db: AsyncSession,
    *,
    email: str,
    google_sub: str | None = None,
    display_name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            google_sub=google_sub,
            display_name=display_name or email.split("@")[0],
            avatar_url=avatar_url,
            coins=0,
            balance_cents=settings.starting_balance_cents,
            pulse_score=settings.starting_pulse_score,
        )
        db.add(user)
    else:
        if google_sub and not user.google_sub:
            user.google_sub = google_sub
        if display_name and not user.display_name:
            user.display_name = display_name
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
    await db.commit()
    # UserOut includes categories. Explicitly load the relationship after the
    # commit so a brand-new account can be serialized on its first login.
    await db.refresh(user, attribute_names=["categories"])
    return user
