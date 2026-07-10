import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.game import market_context
from app.llm import generate_markets_for_category
from app.market_universe import market_has_objects_clause
from app.models import Category, Market, Prediction, User
from app.object_retrieval import search_market_objects
from app.schemas import MarketOut, ObjectOut

router = APIRouter(tags=["feed"])


async def _maybe_topup(user: User, chosen_ids: list[uuid.UUID], db: AsyncSession) -> None:
    """Fire background LLM generation for any chosen category running low on
    unanswered markets for this user. Non-blocking, best-effort."""
    if not settings.llm_enabled:
        return
    answered = select(Prediction.market_id).where(Prediction.user_id == user.id)
    has_universe = market_has_objects_clause()
    now = datetime.now(timezone.utc)
    for cid in chosen_ids:
        remaining = await db.scalar(
            select(func.count())
            .select_from(Market)
            .where(
                Market.category_id == cid,
                Market.status == "open",
                Market.closes_at > now,
                has_universe,
                Market.id.not_in(answered),
            )
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
    has_universe = market_has_objects_clause()
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Market, Category.name, Category.slug, Category.theme)
        .join(Category, Category.id == Market.category_id)
        .where(
            Market.category_id.in_(chosen_ids),
            Market.status == "open",
            Market.closes_at > now,
            has_universe,
            Market.id.not_in(answered),
        )
        .order_by(func.random())
        .limit(limit)
    )
    rows = result.all()
    market_ids = [market.id for market, _, _, _ in rows]

    participant_counts: dict[uuid.UUID, int] = {}
    if market_ids:
        count_result = await db.execute(
            select(Prediction.market_id, func.count(Prediction.id))
            .where(Prediction.market_id.in_(market_ids))
            .group_by(Prediction.market_id)
        )
        participant_counts = {market_id: count for market_id, count in count_result.all()}

    out: list[MarketOut] = []
    for market, cat_name, cat_slug, cat_theme in rows:
        context = market_context(market, participant_counts.get(market.id, 0))
        out.append(
            MarketOut(
                id=market.id,
                prompt=market.prompt,
                object_type=market.object_type,
                category_id=market.category_id,
                category_name=cat_name,
                category_slug=cat_slug,
                category_theme=cat_theme,
                closes_at=market.closes_at,
                participant_count=context["total_call_count"],
                potential_coin_payout=context["potential_payout_max"],
                settle_seconds=context["closes_in_seconds"],
                entry_cost=context["entry_cost"],
                pool_size=context["pool_size"],
                net_pool=context["net_pool"],
                total_call_count=context["total_call_count"],
                closes_in_seconds=context["closes_in_seconds"],
                opens_in_batch_seconds=context["opens_in_batch_seconds"],
                potential_payout_min=context["potential_payout_min"],
                potential_payout_max=context["potential_payout_max"],
                settlement_type=context["settlement_type"],
                is_ranked=context["ranked"],
            )
        )
    return out


@router.get("/search", response_model=list[ObjectOut])
async def search(
    q: str = Query(..., min_length=1),
    market_id: uuid.UUID = Query(...),
    limit: int = Query(16, le=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Market, Category)
        .join(Category, Category.id == Market.category_id)
        .where(
            Market.id == market_id,
            Market.status == "open",
            Market.closes_at > datetime.now(timezone.utc),
            market_has_objects_clause(),
        )
        .limit(1)
    )
    row = result.first()
    if row is None:
        return []

    market, category = row
    objects = await search_market_objects(db, market, category, q, limit)
    return [
        obj
        for obj in objects
        if obj.category_id == market.category_id and obj.object_type == market.object_type
    ]
