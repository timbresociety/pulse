import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import BalanceTransaction, Prediction, User
from app.routers.predictions import reveal_at, reveal_payload, settle_and_reveal
from app.schemas import RevealOut, UserOut

router = APIRouter(prefix="/debug", tags=["debug"])


def _require_debug() -> None:
    if not settings.debug:
        raise HTTPException(404, "Not found")


@router.post("/credits", response_model=UserOut)
async def add_test_credits(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_debug()
    locked_user = (
        await db.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one()
    locked_user.balance_cents += 1_000_000
    db.add(
        BalanceTransaction(
            user_id=locked_user.id,
            transaction_type="test_credit",
            amount_cents=1_000_000,
            balance_after_cents=locked_user.balance_cents,
            reference_key=f"test-credit:{uuid.uuid4()}",
        )
    )
    await db.commit()
    await db.refresh(locked_user)
    return locked_user


@router.post("/predictions/{prediction_id}/resolve", response_model=RevealOut)
async def resolve_now(
    prediction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_debug()
    prediction = (
        await db.execute(
            select(Prediction)
            .where(Prediction.id == prediction_id, Prediction.user_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if prediction is None:
        raise HTTPException(404, "Prediction not found")
    locked_user = (
        await db.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one()
    await settle_and_reveal(db, prediction, locked_user, ignore_timer=True)
    await db.commit()
    return await reveal_payload(db, prediction, locked_user)


@router.post("/resolve-revealable")
async def resolve_revealable(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_debug()
    predictions = (
        await db.execute(
            select(Prediction)
            .where(Prediction.user_id == user.id, Prediction.revealed_at.is_(None))
            .order_by(Prediction.locked_at)
            .with_for_update()
        )
    ).scalars().all()
    locked_user = (
        await db.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one()
    now = datetime.now(timezone.utc)
    count = 0
    for prediction in predictions:
        if now >= reveal_at(prediction):
            await settle_and_reveal(db, prediction, locked_user)
            count += 1
    await db.commit()
    return {"resolved": count}


@router.post("/reset-gameplay")
async def reset_gameplay(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_debug()
    await db.execute(delete(BalanceTransaction).where(BalanceTransaction.user_id == user.id))
    await db.execute(delete(Prediction).where(Prediction.user_id == user.id))
    locked_user = (
        await db.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one()
    locked_user.balance_cents = settings.starting_balance_cents
    locked_user.pulse_score = settings.starting_pulse_score
    await db.commit()
    return {"reset": True, "balance_cents": locked_user.balance_cents, "pulse_score": locked_user.pulse_score}
