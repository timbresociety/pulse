import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.llm import generate_markets_for_category
from app.models import Category, Market, Object, Prediction, User
from app.schemas import (
    CategoryOut,
    HistoryPredictionOut,
    ProfileStatsOut,
    SetCategoriesIn,
    UserOut,
)

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).order_by(Category.sort_order))
    return result.scalars().all()


@router.post("/me/categories", response_model=UserOut)
async def set_categories(
    payload: SetCategoriesIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Category).where(Category.id.in_(payload.category_ids)))
    user.categories = list(result.scalars().all())
    await db.commit()
    await db.refresh(user)

    # Start generating fresh markets for the chosen categories as the user begins.
    if settings.llm_enabled:
        for cid in payload.category_ids:
            asyncio.create_task(generate_markets_for_category(cid))

    return user


@router.get("/me/history", response_model=list[HistoryPredictionOut])
async def history(
    limit: int = Query(50, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Prediction, Market, Category.name, Category.slug, Object.canonical_name)
        .join(Market, Market.id == Prediction.market_id)
        .join(Category, Category.id == Market.category_id)
        .outerjoin(Object, Object.id == Prediction.object_id)
        .where(Prediction.user_id == user.id)
        .order_by(Prediction.locked_at.desc())
        .limit(limit)
    )

    return [
        HistoryPredictionOut(
            id=prediction.id,
            market_id=prediction.market_id,
            prompt=market.prompt,
            category_name=category_name,
            category_slug=category_slug,
            picked_name=picked_name or prediction.raw_text,
            outcome=prediction.outcome,
            locked_at=prediction.locked_at,
            resolved_at=prediction.resolved_at,
            reveal_seconds=prediction.reveal_seconds,
            shown_share=prediction.shown_share,
            coins_won=prediction.coins_won,
            pulse_delta=prediction.pulse_delta,
            payout_multiplier=round((prediction.coins_won or 0) / 10, 1),
            pool_size=0,
        )
        for prediction, market, category_name, category_slug, picked_name in result.all()
    ]


@router.get("/me/stats", response_model=ProfileStatsOut)
async def stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Prediction, Category.name)
        .join(Market, Market.id == Prediction.market_id)
        .join(Category, Category.id == Market.category_id)
        .where(Prediction.user_id == user.id)
    )
    rows = result.all()
    predictions = [prediction for prediction, _category_name in rows]
    resolved_predictions = [p for p in predictions if p.outcome is not None]
    wins = [p for p in resolved_predictions if p.outcome == "win"]
    losses = [p for p in resolved_predictions if p.outcome == "lose"]
    shares = [p.shown_share for p in resolved_predictions if p.shown_share is not None]
    contrarian_wins = [
        p for p in wins
        if p.shown_share is not None and p.shown_share < 0.2
    ]

    streak = 0
    for prediction in sorted(resolved_predictions, key=lambda p: p.resolved_at or p.locked_at, reverse=True):
        if prediction.outcome == "win":
            streak += 1
        else:
            break

    best_category = None
    if rows:
        category_wins = {
            name: sum(1 for prediction, row_name in rows if row_name == name and prediction.outcome == "win")
            for name in {row_name for _prediction, row_name in rows}
        }
        best_category = max(category_wins, key=category_wins.get) if max(category_wins.values(), default=0) else None

    return ProfileStatsOut(
        entered=len(predictions),
        resolved=len(resolved_predictions),
        pending=len(predictions) - len(resolved_predictions),
        wins=len(wins),
        losses=len(losses),
        win_rate=round(len(wins) / len(resolved_predictions), 3) if resolved_predictions else 0,
        total_coins_won=sum(p.coins_won for p in resolved_predictions),
        total_pulse_delta=sum(p.pulse_delta for p in resolved_predictions),
        best_coin_win=max((p.coins_won for p in resolved_predictions), default=0),
        avg_crowd_share=round(sum(shares) / len(shares), 3) if shares else 0,
        current_streak=streak,
        biggest_multiplier=round(max(((p.coins_won or 0) / 10 for p in resolved_predictions), default=0), 1),
        contrarian_wins=len(contrarian_wins),
        best_category=best_category,
    )
