import asyncio
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.llm import generate_markets_for_category
from app.models import Category, Market, Object, ObjectAlias, Prediction, User
from app.schemas import MarketOut, ObjectOut

router = APIRouter(tags=["feed"])


async def _maybe_topup(user: User, chosen_ids: list[uuid.UUID], db: AsyncSession) -> None:
    """Fire background LLM generation for any chosen category running low on
    unanswered markets for this user. Non-blocking, best-effort."""
    if not settings.llm_enabled:
        return
    answered = select(Prediction.market_id).where(Prediction.user_id == user.id)
    for cid in chosen_ids:
        remaining = await db.scalar(
            select(func.count())
            .select_from(Market)
            .where(Market.category_id == cid, Market.id.not_in(answered))
        )
        if (remaining or 0) < settings.feed_topup_threshold:
            asyncio.create_task(generate_markets_for_category(cid))


@router.get("/feed", response_model=list[MarketOut])
async def feed(
    limit: int = Query(20, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chosen_ids = [c.id for c in user.categories]
    if not chosen_ids:
        return []

    await _maybe_topup(user, chosen_ids, db)

    answered = select(Prediction.market_id).where(Prediction.user_id == user.id)
    result = await db.execute(
        select(Market, Category.name, Category.slug)
        .join(Category, Category.id == Market.category_id)
        .where(Market.category_id.in_(chosen_ids), Market.id.not_in(answered))
        .order_by(func.random())
        .limit(limit)
    )
    out: list[MarketOut] = []
    for market, cat_name, cat_slug in result.all():
        out.append(
            MarketOut(
                id=market.id,
                prompt=market.prompt,
                object_type=market.object_type,
                category_id=market.category_id,
                category_name=cat_name,
                category_slug=cat_slug,
            )
        )
    return out


@router.get("/search", response_model=list[ObjectOut])
async def search(
    q: str = Query(..., min_length=1),
    market_id: uuid.UUID = Query(...),
    limit: int = Query(8, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market = await db.get(Market, market_id)
    if market is None:
        return []

    term = q.strip().lower()
    # Trigram similarity over canonical_name and aliases, constrained to the
    # market's object_type + category. Falls back to ILIKE if pg_trgm absent.
    similarity = func.greatest(
        func.similarity(func.lower(Object.canonical_name), term),
        func.coalesce(func.max(func.similarity(func.lower(ObjectAlias.alias), term)), 0.0),
    ).label("sim")

    stmt = (
        select(Object, similarity)
        .outerjoin(ObjectAlias, ObjectAlias.object_id == Object.id)
        .where(
            Object.category_id == market.category_id,
            Object.object_type == market.object_type,
            Object.status == "active",
        )
        .group_by(Object.id)
        .having(
            func.greatest(
                func.similarity(func.lower(Object.canonical_name), term),
                func.coalesce(func.max(func.similarity(func.lower(ObjectAlias.alias), term)), 0.0),
            )
            > 0.1
        )
        .order_by(similarity.desc())
        .limit(limit)
    )
    try:
        result = await db.execute(stmt)
        rows = [row[0] for row in result.all()]
    except Exception:
        # Fallback: simple ILIKE if pg_trgm is unavailable
        await db.rollback()
        like = f"%{term}%"
        result = await db.execute(
            select(Object)
            .where(
                Object.category_id == market.category_id,
                Object.object_type == market.object_type,
                Object.status == "active",
                func.lower(Object.canonical_name).like(like),
            )
            .limit(limit)
        )
        rows = result.scalars().all()
    return rows
