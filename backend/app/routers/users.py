import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.game import ENTRY_COST, RANKED_CALLS_PER_DAY, market_context, user_ranked_calls_today
from app.llm import generate_markets_for_category
from app.models import Category, Market, Object, Prediction, User
from app.schemas import (
    CategoryOut,
    HistoryPredictionOut,
    ProfileStatsOut,
    SetCategoriesIn,
    SetUsernameIn,
    UserOut,
)

router = APIRouter(tags=["users"])


async def _user_out(user: User, db: AsyncSession) -> UserOut:
    ranked_used = await user_ranked_calls_today(db, user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_admin=user.is_admin,
        coins=user.coins,
        pulse_score=user.pulse_score,
        ranked_calls_remaining=max(0, RANKED_CALLS_PER_DAY - ranked_used),
        categories=user.categories,
    )


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _user_out(user, db)


@router.post("/me/username", response_model=UserOut)
async def set_username(
    payload: SetUsernameIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reserved = {"admin", "support", "pulse", "psyblr", "system", "null", "undefined"}
    if payload.username in reserved:
        raise HTTPException(409, "That username is reserved.")
    existing = await db.scalar(
        select(User.id)
        .where(func.lower(User.username) == payload.username)
        .where(User.id != user.id)
        .limit(1)
    )
    if existing is not None:
        raise HTTPException(409, "That username is already taken.")
    user.username = payload.username
    await db.commit()
    await db.refresh(user)
    return await _user_out(user, db)


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

    return await _user_out(user, db)


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

    rows = result.all()
    market_ids = list({market.id for _prediction, market, *_rest in rows})
    call_counts: dict = {}
    if market_ids:
        count_result = await db.execute(
            select(Prediction.market_id, func.count(Prediction.id))
            .where(Prediction.market_id.in_(market_ids))
            .group_by(Prediction.market_id)
        )
        call_counts = {market_id: count for market_id, count in count_result.all()}

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
            entry_cost=ENTRY_COST,
            payout_multiplier=round((prediction.coins_won or 0) / ENTRY_COST, 1),
            pool_size=market_context(market, call_counts.get(market.id, 0))["pool_size"],
            settlement_type="top_call",
        )
        for prediction, market, category_name, category_slug, picked_name in rows
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
    entered = len(predictions)
    resolved_predictions = [p for p in predictions if p.outcome is not None]
    resolved = len(resolved_predictions)
    wins = len([p for p in resolved_predictions if p.outcome == "win"])
    losses = len([p for p in resolved_predictions if p.outcome == "lose"])
    shares = [p.shown_share for p in resolved_predictions if p.shown_share is not None]
    ranked_used = await user_ranked_calls_today(db, user.id)
    streak = 0
    for prediction in sorted(resolved_predictions, key=lambda p: p.resolved_at or p.locked_at, reverse=True):
        if prediction.outcome == "win":
            streak += 1
        else:
            break
    contrarian_wins = len([
        p for p in resolved_predictions
        if p.outcome == "win" and p.shown_share is not None and p.shown_share < 0.2
    ])

    return ProfileStatsOut(
        entered=entered,
        resolved=resolved,
        pending=entered - resolved,
        wins=wins,
        losses=losses,
        win_rate=round(wins / resolved, 3) if resolved else 0,
        total_coins_won=sum(p.coins_won for p in resolved_predictions),
        total_pulse_delta=sum(p.pulse_delta for p in resolved_predictions),
        best_coin_win=max((p.coins_won for p in resolved_predictions), default=0),
        avg_crowd_share=round(sum(shares) / len(shares), 3) if shares else 0,
        ranked_calls_remaining=max(0, RANKED_CALLS_PER_DAY - ranked_used),
        current_streak=streak,
        biggest_multiplier=round(max(((p.coins_won or 0) / ENTRY_COST for p in resolved_predictions), default=0), 1),
        contrarian_wins=contrarian_wins,
        early_calls=0,
        best_category=next(
            (
                category_name
                for category_name, _count in sorted(
                    (
                        (name, sum(1 for prediction, row_name in rows if row_name == name and prediction.outcome == "win"))
                        for name in {name for _prediction, name in rows}
                    ),
                    key=lambda item: (-item[1], item[0]),
                )
                if _count > 0
            ),
            None,
        ),
    )
