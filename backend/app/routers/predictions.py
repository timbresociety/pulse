import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.game import fabricate_reveal, reveal_seconds_for_index, user_locked_count
from app.models import Market, Object, Prediction, User
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
    if payload.object_id is None and not payload.raw_text:
        raise HTTPException(400, "Provide object_id or raw_text")

    index = await user_locked_count(db, user.id)
    reveal_seconds = reveal_seconds_for_index(index)

    prediction = Prediction(
        user_id=user.id,
        market_id=market.id,
        object_id=payload.object_id,
        raw_text=payload.raw_text,
        reveal_seconds=reveal_seconds,
    )
    db.add(prediction)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(409, "Already predicted on this market")
    await db.refresh(prediction)
    return CreatePredictionOut(id=prediction.id, reveal_seconds=reveal_seconds)


@router.post("/{prediction_id}/reveal", response_model=RevealOut)
async def reveal(
    prediction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prediction = await db.get(Prediction, prediction_id)
    if prediction is None or prediction.user_id != user.id:
        raise HTTPException(404, "Prediction not found")

    market = await db.get(Market, prediction.market_id)

    if prediction.outcome is None:
        await fabricate_reveal(db, prediction, market.category_id, market.object_type)
        prediction.resolved_at = datetime.now(timezone.utc)
        user.coins += prediction.coins_won
        user.pulse_score += prediction.pulse_delta
        await db.commit()
        await db.refresh(prediction)
        await db.refresh(user)

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
    )
