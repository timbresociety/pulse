from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import LeaderboardRow

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard", response_model=list[LeaderboardRow])
async def leaderboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Public standings of real accounts that chose a username."""
    result = await db.execute(
        select(User)
        .where(User.username.is_not(None))
        .order_by(User.pulse_score.desc(), User.coins.desc(), User.created_at.asc())
        .limit(100)
    )
    users = result.scalars().all()
    return [
        LeaderboardRow(
            rank=index + 1,
            display_name=row.username or "member",
            coins=row.coins,
            pulse_score=row.pulse_score,
            is_you=row.id == user.id,
        )
        for index, row in enumerate(users)
    ]
