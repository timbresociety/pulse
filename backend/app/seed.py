import json
import os

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import Category, LeaderboardEntry, Market, Object, ObjectAlias
from app.seed_data import BOTS, CATEGORIES, OBJECTS

MARKETS_DIR = os.path.join(os.path.dirname(__file__), "data", "markets")
# A stable, app-specific PostgreSQL advisory lock id. It prevents concurrent
# Vercel cold starts from both attempting the one-time initial seed.
SEED_LOCK_ID = 1_345_391_699


def _load_markets(slug: str) -> list[tuple[str, str]]:
    """Load (prompt, object_type) pairs from app/data/markets/<slug>.json.

    Flattens the subcategory grouping (subcategory is organizational only; the
    demo schema keys markets by category + object_type).
    """
    path = os.path.join(MARKETS_DIR, f"{slug}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    pairs: list[tuple[str, str]] = []
    for questions in data.get("subcategories", {}).values():
        for q in questions:
            pairs.append((q["prompt"], q["object_type"]))
    return pairs


async def seed_if_empty() -> None:
    async with SessionLocal() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": SEED_LOCK_ID})
        count = await db.scalar(select(func.count()).select_from(Category))
        if count and count > 0:
            await db.rollback()
            return
        await _seed(db)


async def _seed(db: AsyncSession) -> None:
    cat_by_slug: dict[str, Category] = {}
    for i, (slug, name, color) in enumerate(CATEGORIES):
        cat = Category(name=name, slug=slug, sort_order=i, theme={"color": color})
        db.add(cat)
        cat_by_slug[slug] = cat
    await db.flush()

    for slug, objects in OBJECTS.items():
        cat = cat_by_slug[slug]
        for canonical_name, object_type, aliases in objects:
            obj = Object(
                canonical_name=canonical_name,
                object_type=object_type,
                category_id=cat.id,
                status="active",
            )
            db.add(obj)
            await db.flush()
            for alias in aliases:
                db.add(ObjectAlias(object_id=obj.id, alias=alias))

    for slug, cat in cat_by_slug.items():
        for prompt, object_type in _load_markets(slug):
            db.add(
                Market(
                    prompt=prompt,
                    category_id=cat.id,
                    object_type=object_type,
                    status="open",
                )
            )

    for name, coins, pulse in BOTS:
        db.add(LeaderboardEntry(display_name=name, coins=coins, pulse_score=pulse, is_bot=True))

    await db.commit()
