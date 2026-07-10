"""Rigged demo game logic: timers, outcomes, fabricated crowd, scoring, coins.

Nothing here reflects a real crowd. Outcomes are weighted-random with dopamine
guardrails; crowd shares are fabricated deterministically per prediction.
"""
import hashlib
import random
import uuid
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Object, Prediction


class DemoMarketMetrics(TypedDict):
    closes_in_seconds: int
    pool_size: int
    total_call_count: int
    potential_payout_max: int
    settlement_type: str


def reveal_seconds_for_index(index: int) -> int:
    """index is 0-based count of the user's prior locked markets.

    30s, 60s, 90s, ... (start + index * increment)
    """
    return settings.reveal_start_seconds + index * settings.reveal_increment_seconds


def _seeded_rng(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def fabricate_market_metrics(market_id: uuid.UUID) -> DemoMarketMetrics:
    """Return a stable fabricated crowd snapshot for a demo market.

    The app deliberately has no real market pool yet, so derive the visible
    crowd from the market id. Keeping it deterministic makes every API surface
    agree on the same numbers without adding mutable demo rows to the database.
    """
    rng = _seeded_rng("market-metrics", market_id)
    total_call_count = rng.randint(24, 120)
    pool_size = total_call_count * 10
    return {
        "closes_in_seconds": rng.randrange(8 * 60, 46 * 60, 30),
        "pool_size": pool_size,
        "total_call_count": total_call_count,
        "potential_payout_max": pool_size - 10,
        "settlement_type": "top_call",
    }


async def user_locked_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(Prediction).where(Prediction.user_id == user_id)
    )
    return result.scalar_one()


async def _recent_outcomes(db: AsyncSession, user_id: uuid.UUID, limit: int) -> list[str]:
    result = await db.execute(
        select(Prediction.outcome)
        .where(Prediction.user_id == user_id, Prediction.outcome.is_not(None))
        .order_by(Prediction.resolved_at.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


async def decide_outcome(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Weighted-random win/lose with dopamine guardrails.

    - The user's very first resolved market is always a win.
    - No two losses back-to-back inside the first `window` resolved markets.
    """
    resolved = await db.execute(
        select(func.count())
        .select_from(Prediction)
        .where(Prediction.user_id == user_id, Prediction.outcome.is_not(None))
    )
    resolved_count = resolved.scalar_one()

    if settings.first_market_always_win and resolved_count == 0:
        return "win"

    rng = _seeded_rng("outcome", user_id, resolved_count)
    outcome = "win" if rng.random() < settings.win_probability else "lose"

    if outcome == "lose" and resolved_count < settings.no_back_to_back_loss_window:
        recent = await _recent_outcomes(db, user_id, 1)
        if recent and recent[0] == "lose":
            outcome = "win"  # avoid back-to-back losses early
    return outcome


async def _random_other_object(
    db: AsyncSession, category_id: uuid.UUID, object_type: str, exclude_id: uuid.UUID | None
) -> Object | None:
    stmt = select(Object).where(
        Object.category_id == category_id,
        Object.object_type == object_type,
        Object.status == "active",
    )
    if exclude_id is not None:
        stmt = stmt.where(Object.id != exclude_id)
    result = await db.execute(stmt.order_by(func.random()).limit(1))
    return result.scalar_one_or_none()


def coins_and_pulse_for_win(shown_share: float, pred_id: uuid.UUID) -> tuple[int, int]:
    """Lower shown share => more 'contrarian' => bigger reward."""
    # contrarian multiplier: share 0.10 -> ~2.2x, share 0.35 -> ~1.1x
    multiplier = max(1.0, 1.0 + (0.40 - shown_share) * 3.0)
    rng = _seeded_rng("payout", pred_id)
    jitter = rng.uniform(0.9, 1.1)
    coins = int(settings.base_coin_payout * multiplier * jitter)
    pulse = int(10 * multiplier * jitter)
    return coins, pulse


async def fabricate_reveal(
    db: AsyncSession,
    prediction: Prediction,
    category_id: uuid.UUID,
    object_type: str,
) -> dict:
    """Decide outcome, fabricate crowd, compute coins/pulse. Mutates prediction."""
    outcome = await decide_outcome(db, prediction.user_id)
    rng = _seeded_rng("crowd", prediction.id)

    if outcome == "win":
        shown_share = round(rng.uniform(0.18, 0.34), 3)
        prediction.shown_winner_object_id = prediction.object_id
        coins, pulse = coins_and_pulse_for_win(shown_share, prediction.id)
    else:
        shown_share = round(rng.uniform(0.22, 0.40), 3)
        other = await _random_other_object(
            db, category_id, object_type, prediction.object_id
        )
        prediction.shown_winner_object_id = other.id if other else None
        coins, pulse = 0, rng.randint(0, 2)

    prediction.outcome = outcome
    prediction.shown_share = shown_share
    prediction.coins_won = coins
    prediction.pulse_delta = pulse
    return {"outcome": outcome, "shown_share": shown_share, "coins_won": coins, "pulse_delta": pulse}
