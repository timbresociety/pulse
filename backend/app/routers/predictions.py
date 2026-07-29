import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.game import (
    PULSE_MARKET_KIND,
    platform_fee_cents,
    reveal_seconds_for_index,
    settle_market,
    simulate_crowd,
    user_locked_count,
    validate_participation,
)
from app.models import BalanceTransaction, Category, Market, MarketOption, Prediction, User
from app.schemas import (
    CreatePredictionIn,
    CreatePredictionOut,
    DifferenceOut,
    DistributionPointOut,
    MarketOptionOut,
    RevealOut,
)

router = APIRouter(prefix="/predictions", tags=["predictions"])


def reveal_at(prediction: Prediction) -> datetime:
    return prediction.locked_at + timedelta(seconds=prediction.reveal_seconds)


async def _market_options(db: AsyncSession, market_id: uuid.UUID) -> list[MarketOption]:
    result = await db.execute(
        select(MarketOption)
        .where(MarketOption.market_id == market_id)
        .order_by(MarketOption.display_order)
    )
    return list(result.scalars().all())


@router.post("", response_model=CreatePredictionOut, status_code=201)
async def lock_prediction(
    payload: CreatePredictionIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market = await db.get(Market, payload.market_id)
    if market is None:
        raise HTTPException(404, "Market not found")
    if market.market_kind != PULSE_MARKET_KIND or market.status != "active":
        raise HTTPException(409, "Market is not active")

    options = await _market_options(db, market.id)
    locked_user = (
        await db.execute(select(User).where(User.id == user.id).with_for_update())
    ).scalar_one()
    try:
        validate_participation(
            [option.id for option in options],
            payload.vote_option_id,
            payload.forecast_bps,
            payload.stake_cents,
            locked_user.balance_cents,
        )
    except ValueError as error:
        status_code = 402 if "balance" in str(error).lower() else 400
        raise HTTPException(status_code, str(error))

    duplicate = await db.scalar(
        select(Prediction.id).where(
            Prediction.user_id == locked_user.id,
            Prediction.market_id == market.id,
        )
    )
    if duplicate:
        raise HTTPException(409, "You already participated in this market")

    index = await user_locked_count(db, locked_user.id)
    delay = reveal_seconds_for_index(index)
    fee = platform_fee_cents(payload.stake_cents)
    now = datetime.now(timezone.utc)
    prediction = Prediction(
        user_id=locked_user.id,
        market_id=market.id,
        vote_option_id=payload.vote_option_id,
        forecast_bps={str(key): value for key, value in payload.forecast_bps.items()},
        stake_cents=payload.stake_cents,
        user_fee_cents=fee,
        reveal_seconds=delay,
        locked_at=now,
    )
    locked_user.balance_cents -= payload.stake_cents
    db.add(prediction)
    try:
        await db.flush()
        db.add(
            BalanceTransaction(
                user_id=locked_user.id,
                prediction_id=prediction.id,
                transaction_type="stake",
                amount_cents=-payload.stake_cents,
                balance_after_cents=locked_user.balance_cents,
                reference_key=f"stake:{prediction.id}",
            )
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "You already participated in this market")
    await db.refresh(prediction)
    return CreatePredictionOut(
        id=prediction.id,
        reveal_seconds=delay,
        locked_at=prediction.locked_at,
        stake_cents=prediction.stake_cents or 0,
        user_fee_cents=prediction.user_fee_cents or 0,
        new_balance_cents=locked_user.balance_cents,
    )


async def settle_and_reveal(
    db: AsyncSession,
    prediction: Prediction,
    user: User,
    *,
    ignore_timer: bool = False,
) -> None:
    """Settle, reveal, credit and score once. Caller owns the transaction."""
    now = datetime.now(timezone.utc)
    if prediction.revealed_at is not None and prediction.payout_credited_at is not None:
        return
    if not ignore_timer and now < reveal_at(prediction):
        seconds = max(1, int((reveal_at(prediction) - now).total_seconds()))
        raise HTTPException(409, f"Reveal available in {seconds} seconds")

    market = await db.get(Market, prediction.market_id)
    if market is None or market.market_kind != PULSE_MARKET_KIND:
        raise HTTPException(409, "Legacy predictions use the legacy reveal path")
    options = await _market_options(db, market.id)

    if prediction.settled_at is None:
        crowd = simulate_crowd(
            market.id,
            [option.id for option in options],
            market.simulation_weights_bps or [],
        )
        settlement = settle_market(
            crowd,
            option_ids=[option.id for option in options],
            user_vote_option_id=prediction.vote_option_id,
            user_forecast_bps=prediction.forecast_bps or {},
            user_stake_cents=prediction.stake_cents or 0,
        )
        prediction.gross_pool_cents = settlement.gross_pool_cents
        prediction.net_pool_cents = settlement.net_pool_cents
        prediction.actual_distribution_bps = settlement.actual_distribution_bps
        prediction.forecast_error = settlement.forecast_error
        prediction.accuracy_multiplier = settlement.accuracy_multiplier
        prediction.accuracy_score = settlement.accuracy_score
        prediction.accuracy_percentile = settlement.accuracy_percentile
        prediction.forecast_rank = settlement.forecast_rank
        prediction.total_participants = settlement.total_participants
        prediction.user_fee_cents = settlement.user_fee_cents
        prediction.payout_cents = settlement.payout_cents
        prediction.pnl_cents = settlement.pnl_cents
        prediction.pulse_delta = settlement.pulse_delta
        prediction.outcome = "win" if settlement.pnl_cents >= 0 else "lose"
        prediction.settled_at = now
        prediction.resolved_at = now

    if prediction.payout_credited_at is None:
        payout = prediction.payout_cents or 0
        user.balance_cents += payout
        user.pulse_score += prediction.pulse_delta
        prediction.payout_credited_at = now
        prediction.revealed_at = now
        db.add(
            BalanceTransaction(
                user_id=user.id,
                prediction_id=prediction.id,
                transaction_type="payout",
                amount_cents=payout,
                balance_after_cents=user.balance_cents,
                reference_key=f"payout:{prediction.id}",
            )
        )
    elif prediction.revealed_at is None:
        prediction.revealed_at = prediction.payout_credited_at


async def reveal_payload(
    db: AsyncSession, prediction: Prediction, user: User
) -> RevealOut:
    market = await db.get(Market, prediction.market_id)
    category = await db.get(Category, market.category_id)
    options = await _market_options(db, market.id)
    vote = next(option for option in options if option.id == prediction.vote_option_id)
    forecast_map = prediction.forecast_bps or {}
    actual_map = prediction.actual_distribution_bps or {}
    forecast_points = [
        DistributionPointOut(
            option_id=option.id,
            key=option.option_key,
            label=option.label,
            bps=forecast_map[str(option.id)],
        )
        for option in options
    ]
    actual_points = [
        DistributionPointOut(
            option_id=option.id,
            key=option.option_key,
            label=option.label,
            bps=actual_map[str(option.id)],
        )
        for option in options
    ]
    differences = sorted(
        [
            DifferenceOut(
                option_id=option.id,
                label=option.label,
                forecast_bps=forecast_map[str(option.id)],
                actual_bps=actual_map[str(option.id)],
                difference_bps=forecast_map[str(option.id)] - actual_map[str(option.id)],
            )
            for option in options
        ],
        key=lambda difference: abs(difference.difference_bps),
        reverse=True,
    )[:3]
    return RevealOut(
        prediction_id=prediction.id,
        market_id=market.id,
        question=market.question or market.prompt,
        category_name=category.name,
        vote=MarketOptionOut(
            id=vote.id, key=vote.option_key, label=vote.label, display_order=vote.display_order
        ),
        forecast=forecast_points,
        actual_distribution=actual_points,
        largest_differences=differences,
        accuracy_score=prediction.accuracy_score or 0,
        accuracy_percentile=prediction.accuracy_percentile or 0,
        forecast_rank=prediction.forecast_rank or 0,
        total_participants=prediction.total_participants or 0,
        stake_cents=prediction.stake_cents or 0,
        user_fee_cents=prediction.user_fee_cents or 0,
        gross_pool_cents=prediction.gross_pool_cents or 0,
        net_pool_cents=prediction.net_pool_cents or 0,
        payout_cents=prediction.payout_cents or 0,
        pnl_cents=prediction.pnl_cents or 0,
        pulse_delta=prediction.pulse_delta,
        new_balance_cents=user.balance_cents,
        new_pulse_score=user.pulse_score,
        revealed_at=prediction.revealed_at or datetime.now(timezone.utc),
    )


@router.post("/{prediction_id}/reveal", response_model=RevealOut)
async def reveal(
    prediction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    await settle_and_reveal(db, prediction, locked_user)
    try:
        await db.commit()
    except IntegrityError:
        # A retried request can race with the unique payout ledger insert. The
        # persisted credit remains the source of truth.
        await db.rollback()
    prediction = await db.get(Prediction, prediction_id)
    locked_user = await db.get(User, user.id)
    return await reveal_payload(db, prediction, locked_user)
