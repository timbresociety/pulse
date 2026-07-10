import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.game import (
    ENTRY_COST,
    RANKED_CALLS_PER_DAY,
    market_context,
    settle_market,
    user_ranked_calls_today,
)
from app.market_universe import market_has_object, market_universe_is_valid
from app.models import Category, Market, Object, Prediction, User
from app.object_retrieval import resolve_market_object
from app.schemas import CreatePredictionIn, CreatePredictionOut, RevealOut

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("", response_model=CreatePredictionOut)
async def lock_prediction(
    payload: CreatePredictionIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market = await db.get(Market, payload.market_id)
    if market is None:
        raise HTTPException(404, "Market not found")
    if market.status != "open":
        raise HTTPException(400, "Market is not open")
    if market.closes_at is None or market.closes_at <= datetime.now(timezone.utc):
        raise HTTPException(400, "This market is closed")
    if not await market_universe_is_valid(db, market):
        raise HTTPException(409, "This market's answer universe is unavailable")
    if payload.object_id is None and not payload.raw_text:
        raise HTTPException(400, "Provide object_id or raw_text")

    picked_object: Object | None = None
    if payload.object_id is not None:
        picked_object = await db.get(Object, payload.object_id)
        if (
            picked_object is None
            or not await market_has_object(db, market.id, payload.object_id)
        ):
            raise HTTPException(400, "Object is not valid for this market")
    else:
        category = await db.get(Category, market.category_id)
        if category is None:
            raise HTTPException(404, "Category not found")
        picked_object = await resolve_market_object(db, market, category, payload.raw_text or "")
        if picked_object is None:
            raise HTTPException(422, "No relevant object found for this market")

    if user.coins < ENTRY_COST:
        raise HTTPException(402, "Not enough coins to enter this market")

    existing_call_count = await db.scalar(
        select(func.count()).select_from(Prediction).where(Prediction.market_id == market.id)
    )
    context = market_context(market, existing_call_count or 0)
    ranked_used = await user_ranked_calls_today(db, user.id)
    is_ranked = ranked_used < RANKED_CALLS_PER_DAY and context["ranked"]
    reveal_seconds = context["closes_in_seconds"]

    prediction = Prediction(
        user_id=user.id,
        market_id=market.id,
        object_id=picked_object.id,
        raw_text=None,
        reveal_seconds=reveal_seconds,
    )
    db.add(prediction)
    user.coins -= ENTRY_COST
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(409, "Already predicted on this market")
    await db.refresh(prediction)
    await db.refresh(user)
    return CreatePredictionOut(
        id=prediction.id,
        reveal_seconds=reveal_seconds,
        new_coins=user.coins,
        entry_cost=ENTRY_COST,
        is_ranked=is_ranked,
        ranked_calls_remaining=max(0, RANKED_CALLS_PER_DAY - ranked_used - 1),
        pool_size=context["pool_size"] + ENTRY_COST,
        object_id=picked_object.id,
        canonical_name=picked_object.canonical_name,
        object_type=picked_object.object_type,
    )


@router.post("/{prediction_id}/reveal", response_model=RevealOut)
async def reveal(
    prediction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prediction = await db.get(Prediction, prediction_id)
    if prediction is None or prediction.user_id != user.id:
        raise HTTPException(404, "Prediction not found")

    if prediction.outcome is None:
        market = await db.scalar(
            select(Market).where(Market.id == prediction.market_id).with_for_update()
        )
        if market is None:
            raise HTTPException(404, "Market not found")
        await settle_market(db, market)
        await db.commit()
        await db.refresh(prediction)
        await db.refresh(user)
    else:
        market = await db.get(Market, prediction.market_id)
        if market is None:
            raise HTTPException(404, "Market not found")

    your_pick = None
    if prediction.object_id:
        obj = await db.get(Object, prediction.object_id)
        your_pick = obj.canonical_name if obj else None
    else:
        your_pick = prediction.raw_text

    winning = None
    if prediction.shown_winner_object_id:
        wobj = await db.get(Object, prediction.shown_winner_object_id)
        winning = wobj.canonical_name if wobj else None
    elif prediction.outcome == "win":
        winning = prediction.raw_text

    return RevealOut(
        prediction_id=prediction.id,
        outcome=prediction.outcome,
        your_pick=your_pick,
        winning_object=winning,
        shown_share=prediction.shown_share or 0.0,
        coins_won=prediction.coins_won,
        pulse_delta=prediction.pulse_delta,
        new_coins=user.coins,
        new_pulse=user.pulse_score,
        entry_cost=ENTRY_COST,
        payout_multiplier=round((prediction.coins_won or 0) / ENTRY_COST, 1),
        pool_size=market_context(
            market,
            await db.scalar(
                select(func.count()).select_from(Prediction).where(Prediction.market_id == market.id)
            ) or 0,
        )["pool_size"],
        settlement_type="top_call",
        taste_signal=(
            "The market settled on another canonical call."
            if prediction.outcome != "win"
            else "Your call matched the market result."
        ),
    )
