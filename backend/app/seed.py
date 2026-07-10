import json
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.config import settings
from app.market_universe import (
    catalog_source,
    create_market_with_universe,
    market_universe_is_valid,
    provision_existing_market_universe,
)
from app.models import Category, Market, Object, ObjectAlias
from app.seed_data import CATEGORIES, OBJECTS

MARKETS_DIR = os.path.join(os.path.dirname(__file__), "data", "markets")


_UNBOUNDED_TIME_MARKERS = ("this year", "right now", "2010s", "2020s")


def _load_markets(slug: str) -> list[tuple[str, str]]:
    """Load only catalog-wide markets with a provable answer universe."""
    path = os.path.join(MARKETS_DIR, f"{slug}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    questions = data.get("subcategories", {}).get("all-time", [])
    return [
        (q["prompt"], q["object_type"])
        for q in questions
        if not any(marker in q["prompt"].lower() for marker in _UNBOUNDED_TIME_MARKERS)
    ]


async def seed_if_empty() -> None:
    async with SessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(Category))
        if count and count > 0:
            await _ensure_catalog(db)
            return
        await _seed(db)


def _lookup_key(value: str) -> str:
    return " ".join(value.lower().strip().split())


def _object_types_for_slug(slug: str) -> set[str]:
    return {object_type for _name, object_type, _aliases in _iter_catalog_objects(slug)}


def _iter_catalog_objects(slug: str):
    for canonical_name, object_types, aliases in OBJECTS.get(slug, []):
        if isinstance(object_types, str):
            object_types = (object_types,)
        for object_type in object_types:
            yield canonical_name, object_type, aliases


async def _sync_aliases(db: AsyncSession, obj: Object, aliases: list[str]) -> None:
    await db.execute(delete(ObjectAlias).where(ObjectAlias.object_id == obj.id))
    seen: set[str] = set()
    for alias in [obj.canonical_name, *aliases]:
        alias_key = _lookup_key(alias)
        if alias_key and alias_key not in seen:
            db.add(ObjectAlias(object_id=obj.id, alias=alias))
            seen.add(alias_key)


async def _ensure_catalog(db: AsyncSession) -> None:
    cat_by_slug: dict[str, Category] = {}
    for i, (slug, name, color) in enumerate(CATEGORIES):
        cat = await db.scalar(select(Category).where(Category.slug == slug).limit(1))
        if cat is None:
            cat = Category(name=name, slug=slug, sort_order=i, theme={"color": color})
            db.add(cat)
            await db.flush()
        else:
            cat.name = name
            cat.sort_order = i
            cat.theme = {"color": color}
        cat_by_slug[slug] = cat

    for slug in OBJECTS:
        cat = cat_by_slug[slug]
        for canonical_name, object_type, aliases in _iter_catalog_objects(slug):
            obj = await db.scalar(
                select(Object)
                .where(
                    Object.category_id == cat.id,
                    Object.object_type == object_type,
                    func.lower(Object.canonical_name) == canonical_name.lower(),
                )
                .limit(1)
            )
            if obj is None:
                obj = Object(
                    canonical_name=canonical_name,
                    object_type=object_type,
                    category_id=cat.id,
                    object_metadata={"source": "initial_catalog", "entity_key": _lookup_key(canonical_name)},
                    status="active",
                )
                db.add(obj)
                await db.flush()
            else:
                obj.status = "active"
                obj.object_metadata = {"source": "initial_catalog", "entity_key": _lookup_key(canonical_name)}

            await _sync_aliases(db, obj, aliases)

    await _ensure_markets(db, cat_by_slug)
    await db.commit()


async def _ensure_markets(db: AsyncSession, cat_by_slug: dict[str, Category]) -> None:
    for slug, cat in cat_by_slug.items():
        valid_types = _object_types_for_slug(slug)
        if not valid_types:
            continue

        existing_result = await db.execute(
            select(Market).where(Market.category_id == cat.id)
        )
        existing_markets = existing_result.scalars().all()
        existing_by_key = {
            (_lookup_key(market.prompt), market.object_type): market
            for market in existing_markets
        }
        catalog_wide_keys = {
            (_lookup_key(prompt), object_type)
            for prompt, object_type in _load_markets(slug)
            if object_type in valid_types
        }

        for prompt, object_type in _load_markets(slug):
            if object_type not in valid_types:
                continue
            key = (_lookup_key(prompt), object_type)
            market = existing_by_key.get(key)
            if market is None:
                await create_market_with_universe(
                    db,
                    prompt=prompt,
                    category_id=cat.id,
                    object_type=object_type,
                    source=catalog_source(),
                    closes_at=datetime.now(timezone.utc)
                    + timedelta(minutes=settings.default_market_duration_minutes),
                )
            else:
                await provision_existing_market_universe(db, market)

        for market in existing_markets:
            key = (_lookup_key(market.prompt), market.object_type)
            if market.object_type not in valid_types:
                market.status = "closed"
            elif key in catalog_wide_keys:
                await provision_existing_market_universe(db, market)
            elif await market_universe_is_valid(db, market):
                market.status = "open"
            else:
                market.status = "closed"


async def _seed(db: AsyncSession) -> None:
    cat_by_slug: dict[str, Category] = {}
    for i, (slug, name, color) in enumerate(CATEGORIES):
        cat = Category(name=name, slug=slug, sort_order=i, theme={"color": color})
        db.add(cat)
        cat_by_slug[slug] = cat
    await db.flush()

    for slug in OBJECTS:
        cat = cat_by_slug[slug]
        for canonical_name, object_type, aliases in _iter_catalog_objects(slug):
            obj = Object(
                canonical_name=canonical_name,
                object_type=object_type,
                category_id=cat.id,
                object_metadata={"source": "initial_catalog", "entity_key": _lookup_key(canonical_name)},
                status="active",
            )
            db.add(obj)
            await db.flush()
            await _sync_aliases(db, obj, aliases)

    await _ensure_markets(db, cat_by_slug)

    await db.commit()
