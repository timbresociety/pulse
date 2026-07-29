from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.game import PULSE_MARKET_KIND
from app.leaderboard_data import (
    LeaderboardProfile,
    complete_dummy_field,
    ranked_window,
)
from app.models import LeaderboardEntry, Market, Prediction, User
from app.schemas import LeaderboardOut, LeaderboardRow

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard", response_model=LeaderboardOut)
async def leaderboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bots = (
        await db.execute(
            select(LeaderboardEntry).where(LeaderboardEntry.is_bot.is_(True))
        )
    ).scalars().all()
    predictions = (
        await db.execute(
            select(Prediction)
            .join(Market, Market.id == Prediction.market_id)
            .where(
                Prediction.user_id == user.id,
                Market.market_kind == PULSE_MARKET_KIND,
            )
            .order_by(Prediction.locked_at)
        )
    ).scalars().all()
    revealed = [prediction for prediction in predictions if prediction.revealed_at]
    wins = [prediction for prediction in revealed if (prediction.pnl_cents or 0) >= 0]
    streak = 0
    for prediction in reversed(revealed):
        if (prediction.pnl_cents or 0) >= 0:
            streak += 1
        else:
            break

    dummy_profiles = complete_dummy_field(
        [
            LeaderboardProfile(
                display_name=bot.display_name,
                avatar_url=bot.avatar_url,
                pulse_score=bot.pulse_score,
                average_accuracy=bot.average_accuracy,
                win_rate=bot.win_rate,
                markets_played=bot.markets_played,
                current_streak=bot.current_streak,
            )
            for bot in bots
        ],
        starting_pulse_score=settings.starting_pulse_score,
    )
    user_profile = LeaderboardProfile(
        display_name=user.display_name or user.email.split("@")[0],
        avatar_url=user.avatar_url,
        pulse_score=user.pulse_score,
        average_accuracy=(
            sum(prediction.accuracy_score or 0 for prediction in revealed) / len(revealed)
            if revealed
            else 0
        ),
        win_rate=len(wins) / len(revealed) if revealed else 0,
        markets_played=len(predictions),
        current_streak=streak,
        is_you=True,
    )
    total_players, user_rank, rows = ranked_window(dummy_profiles, user_profile)
    return LeaderboardOut(
        total_players=total_players,
        user_rank=user_rank,
        rows=[LeaderboardRow(**row) for row in rows],
    )
