import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.llm import generate_markets_for_category
from app.models import Category, User
from app.schemas import CategoryOut, SetCategoriesIn, UserOut

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


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

    return user
