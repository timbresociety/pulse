from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import LeaderboardEntry, User
from app.schemas import LeaderboardRow

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard", response_model=list[LeaderboardRow])
async def leaderboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    metric = settings.leaderboard_rank_metric
    result = await db.execute(select(LeaderboardEntry))
    bots = result.scalars().all()

    rows = [
        {"display_name": b.display_name, "coins": b.coins, "pulse_score": b.pulse_score, "is_you": False}
        for b in bots
    ]
    rows.append(
        {
            "display_name": user.display_name or user.email.split("@")[0],
            "coins": user.coins,
            "pulse_score": user.pulse_score,
            "is_you": True,
        }
    )

    key = "coins" if metric == "coins" else "pulse_score"
    rows.sort(key=lambda r: r[key], reverse=True)

    return [
        LeaderboardRow(rank=i + 1, **r) for i, r in enumerate(rows)
    ]
