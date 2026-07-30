import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.auth import get_current_user, get_current_user_with_categories
from app.config import settings
from app.database import get_db
from app.game import (
    PULSE_MARKET_KIND,
    market_avatar_names,
    reveal_seconds_for_index,
    simulate_crowd,
)
from app.models import Category, Market, Object, ObjectAlias, Prediction, User
from app.schemas import MarketCategoryOut, MarketOptionOut, MarketOut, ObjectOut

router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=list[MarketOut], response_model_exclude_none=True)
async def feed(
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user_with_categories),
    db: AsyncSession = Depends(get_db),
):
    chosen_ids = [category.id for category in user.categories if category.is_active]
    if not chosen_ids:
        return []

    answered = select(Prediction.market_id).where(Prediction.user_id == user.id)
    locked_count = (
        select(func.count(Prediction.id))
        .where(Prediction.user_id == user.id)
        .scalar_subquery()
    )
    result = await db.execute(
        select(Market, Category, locked_count)
        .join(Category, Category.id == Market.category_id)
        .where(
            Market.category_id.in_(chosen_ids),
            Market.market_kind == PULSE_MARKET_KIND,
            Market.status == "active",
            Category.is_active.is_(True),
            Market.id.not_in(answered),
        )
        .order_by(Market.created_at, Market.market_key)
        .limit(limit)
        .options(joinedload(Market.options))
    )
    output: list[MarketOut] = []
    for market, category, index in result.unique().all():
        reveal_seconds = reveal_seconds_for_index(index)
        options = sorted(market.options, key=lambda option: option.display_order)
        crowd = simulate_crowd(
            market.id,
            [option.id for option in options],
            market.simulation_weights_bps or [],
        )
        option_output = [
            MarketOptionOut(
                id=option.id,
                key=option.option_key,
                label=option.label,
                display_order=option.display_order,
            )
            for option in options
        ]
        output.append(
            MarketOut(
                id=market.id,
                key=market.market_key or str(market.id),
                question=market.question or market.prompt,
                context=market.context,
                category=MarketCategoryOut(id=category.id, slug=category.slug, name=category.name),
                options=option_output,
                participant_count=crowd.participant_count,
                pool_volume_cents=crowd.pool_volume_cents,
                net_pool_volume_cents=crowd.net_pool_volume_cents,
                reveal_seconds=reveal_seconds,
                avatars=market_avatar_names(market.id),
                simulation_seed=crowd.seed if settings.debug else None,
                latent_distribution_bps=crowd.latent_distribution_bps if settings.debug else None,
            )
        )
    return output


@router.get("/search", response_model=list[ObjectOut])
async def search(
    q: str = Query(..., min_length=1),
    market_id: uuid.UUID = Query(...),
    limit: int = Query(8, le=20),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Legacy compatibility endpoint; Pulse Poll markets never use object search."""
    market = await db.get(Market, market_id)
    if market is None or market.market_kind == PULSE_MARKET_KIND:
        return []

    term = q.strip().lower()
    similarity = func.greatest(
        func.similarity(func.lower(Object.canonical_name), term),
        func.coalesce(func.max(func.similarity(func.lower(ObjectAlias.alias), term)), 0.0),
    ).label("sim")
    statement = (
        select(Object, similarity)
        .outerjoin(ObjectAlias, ObjectAlias.object_id == Object.id)
        .where(
            Object.category_id == market.category_id,
            Object.object_type == market.object_type,
            Object.status == "active",
        )
        .group_by(Object.id)
        .order_by(similarity.desc())
        .limit(limit)
    )
    try:
        rows = (await db.execute(statement)).all()
        return [row[0] for row in rows]
    except Exception:
        await db.rollback()
        result = await db.execute(
            select(Object)
            .where(
                Object.category_id == market.category_id,
                Object.object_type == market.object_type,
                Object.status == "active",
                func.lower(Object.canonical_name).like(f"%{term}%"),
            )
            .limit(limit)
        )
        return result.scalars().all()
