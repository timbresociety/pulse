"""Real market accounting and settlement.

Every displayed call count, pool, winner, payout, and leaderboard score is
derived from persisted user predictions. Markets settle once, after their actual
close time; no manufactured participation or outcome shaping is used.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Market, Prediction, User

ENTRY_COST = 10
RANKED_CALLS_PER_DAY = 10
PLATFORM_RAKE = 0.10


def market_context(market: Market, total_calls: int = 0) -> dict:
    now = datetime.now(timezone.utc)
    closes_in = max(
        0,
        int((market.closes_at - now).total_seconds()),
    ) if market.closes_at else 0
    pool = total_calls * ENTRY_COST
    net_pool = int(pool * (1 - PLATFORM_RAKE))
    # This is deliberately the current distributable pool, not an invented
    # payout projection. The final distribution depends on real winning calls.
    return {
        "entry_cost": ENTRY_COST,
        "ranked": True,
        "closes_in_seconds": closes_in,
        "opens_in_batch_seconds": 0,
        "total_call_count": total_calls,
        "pool_size": pool,
        "net_pool": net_pool,
        "potential_payout_min": 0,
        "potential_payout_max": net_pool,
        "settlement_type": "top_call",
    }


async def user_ranked_calls_today(db: AsyncSession, user_id: uuid.UUID) -> int:
    start = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    result = await db.execute(
        select(func.count())
        .select_from(Prediction)
        .where(Prediction.user_id == user_id, Prediction.locked_at >= start)
    )
    return result.scalar_one()


async def settle_market(db: AsyncSession, market: Market) -> None:
    """Settle a closed market from its persisted calls exactly once.

    Ties use the object whose first call was locked earliest. The full tie rule
    is deterministic so any worker/API request reaches the same result.
    """
    now = datetime.now(timezone.utc)
    if market.settled_at is not None or market.status == "settled":
        return
    if market.closes_at is None or now < market.closes_at:
        raise HTTPException(409, "This market has not closed yet.")

    result = await db.execute(
        select(Prediction)
        .where(Prediction.market_id == market.id)
        .order_by(Prediction.locked_at.asc(), Prediction.id.asc())
        .with_for_update()
    )
    predictions = result.scalars().all()
    if not predictions:
        market.status = "settled"
        market.settled_at = now
        return

    counts: dict[uuid.UUID, int] = {}
    first_call: dict[uuid.UUID, tuple[datetime, str]] = {}
    for prediction in predictions:
        if prediction.object_id is None:
            continue
        counts[prediction.object_id] = counts.get(prediction.object_id, 0) + 1
        first_call.setdefault(prediction.object_id, (prediction.locked_at, str(prediction.id)))

    if not counts:
        market.status = "settled"
        market.settled_at = now
        return

    winner_id = min(
        counts,
        key=lambda object_id: (-counts[object_id], first_call[object_id][0], first_call[object_id][1]),
    )
    winner_count = counts[winner_id]
    shown_share = round(winner_count / len(predictions), 3)
    distributable_pool = int(len(predictions) * ENTRY_COST * (1 - PLATFORM_RAKE))
    per_winner, remainder = divmod(distributable_pool, winner_count)
    winner_predictions = [p for p in predictions if p.object_id == winner_id]

    winner_positions = {prediction.id: index for index, prediction in enumerate(winner_predictions)}
    for prediction in predictions:
        won = prediction.object_id == winner_id
        coins = (
            per_winner + (1 if winner_positions[prediction.id] < remainder else 0)
            if won
            else 0
        )
        pulse = 10 if won else 0
        prediction.outcome = "win" if won else "lose"
        prediction.shown_winner_object_id = winner_id
        prediction.shown_share = shown_share
        prediction.coins_won = coins
        prediction.pulse_delta = pulse
        prediction.resolved_at = now
        if won:
            await db.execute(
                update(User)
                .where(User.id == prediction.user_id)
                .values(coins=User.coins + coins, pulse_score=User.pulse_score + pulse)
            )

    market.winning_object_id = winner_id
    market.status = "settled"
    market.settled_at = now
