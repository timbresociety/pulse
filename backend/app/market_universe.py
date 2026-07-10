"""Source-bound, finite answer universes for markets.

Search is intentionally restricted to `MarketObject` rows. A market can only be
opened through this module after the creator supplies its scoped source and an
explicit, non-overlapping list of valid objects.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Market, MarketObject, MarketUniverse, Object, Prediction

MIN_MARKET_OBJECTS = 3


@dataclass(frozen=True)
class UniverseSource:
    source_name: str
    source_url: str
    scope_statement: str
    coverage_statement: str
    source_updated_at: datetime
    created_by_user_id: uuid.UUID | None = None


def _canonical_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _coverage_hash(objects: Sequence[Object]) -> str:
    payload = "\n".join(sorted(_canonical_key(obj.canonical_name) for obj in objects))
    return hashlib.sha256(payload.encode()).hexdigest()


def catalog_source() -> UniverseSource:
    """Provenance for the initial curated catalog, including migrated rows."""
    return UniverseSource(
        source_name="Pulse curated catalog",
        source_url="https://pulse.local/curated-catalog",
        scope_statement="The published catalog for this market's category and object type.",
        coverage_statement="Each listed object is a distinct canonical answer in the declared scope.",
        source_updated_at=datetime.now(timezone.utc),
    )


async def _catalog_objects_for_market(db: AsyncSession, market: Market) -> list[Object]:
    result = await db.execute(
        select(Object).where(
            Object.category_id == market.category_id,
            Object.object_type == market.object_type,
            Object.status == "active",
        )
    )
    return result.scalars().all()


def _is_valid_object_set(market: Market, objects: Sequence[Object]) -> bool:
    if len(objects) < MIN_MARKET_OBJECTS:
        return False
    if any(
        obj.category_id != market.category_id
        or obj.object_type != market.object_type
        or obj.status != "active"
        for obj in objects
    ):
        return False
    return len({_canonical_key(obj.canonical_name) for obj in objects}) == len(objects)


async def _upsert_universe(
    db: AsyncSession,
    *,
    market: Market,
    objects: Sequence[Object],
    source: UniverseSource,
) -> MarketUniverse:
    universe = await db.scalar(select(MarketUniverse).where(MarketUniverse.market_id == market.id))
    values = {
        "source_name": source.source_name.strip(),
        "source_url": source.source_url.strip(),
        "scope_statement": source.scope_statement.strip(),
        "coverage_statement": source.coverage_statement.strip(),
        "source_updated_at": source.source_updated_at,
        "coverage_hash": _coverage_hash(objects),
        "object_count": len(objects),
        "created_by_user_id": source.created_by_user_id,
    }
    if universe is None:
        universe = MarketUniverse(market_id=market.id, **values)
        db.add(universe)
    else:
        for key, value in values.items():
            setattr(universe, key, value)
    await db.flush()
    return universe


async def market_universe_is_valid(db: AsyncSession, market: Market) -> bool:
    universe = await db.scalar(select(MarketUniverse).where(MarketUniverse.market_id == market.id))
    if universe is None or not universe.source_url or not universe.scope_statement:
        return False
    result = await db.execute(
        select(Object)
        .join(MarketObject, MarketObject.object_id == Object.id)
        .where(MarketObject.market_id == market.id)
    )
    objects = result.scalars().all()
    return (
        universe.object_count == len(objects)
        and universe.coverage_hash == _coverage_hash(objects)
        and _is_valid_object_set(market, objects)
    )


async def market_has_object(
    db: AsyncSession,
    market_id: uuid.UUID,
    object_id: uuid.UUID,
) -> bool:
    return bool(
        await db.scalar(
            select(MarketObject.id)
            .where(
                MarketObject.market_id == market_id,
                MarketObject.object_id == object_id,
            )
            .limit(1)
        )
    )


def market_has_objects_clause():
    """SQL predicate used on feed/search paths to exclude incomplete markets."""
    object_count = (
        select(func.count(MarketObject.id))
        .where(MarketObject.market_id == Market.id)
        .correlate(Market)
        .scalar_subquery()
    )
    has_universe = exists(
        select(MarketUniverse.id).where(
            MarketUniverse.market_id == Market.id,
            MarketUniverse.object_count >= MIN_MARKET_OBJECTS,
        )
    )
    return and_(has_universe, object_count >= MIN_MARKET_OBJECTS)


async def create_market_with_universe(
    db: AsyncSession,
    *,
    prompt: str,
    category_id: uuid.UUID,
    object_type: str,
    source: UniverseSource,
    object_ids: Sequence[uuid.UUID] | None = None,
    closes_at: datetime | None = None,
) -> Market | None:
    """Create a market atomically with its declared answer universe.

    Passing a source is mandatory. The method returns `None` rather than
    publishing a partly-valid market when the list cannot be validated.
    """
    market = Market(
        prompt=prompt.strip(),
        category_id=category_id,
        object_type=object_type.strip().casefold(),
        status="open",
        closes_at=closes_at,
    )
    db.add(market)
    await db.flush()

    if object_ids is None:
        objects = await _catalog_objects_for_market(db, market)
    else:
        result = await db.execute(select(Object).where(Object.id.in_(object_ids)))
        objects = result.scalars().all()

    if not _is_valid_object_set(market, objects):
        await db.delete(market)
        await db.flush()
        return None

    db.add_all(MarketObject(market_id=market.id, object_id=obj.id) for obj in objects)
    await db.flush()
    await _upsert_universe(db, market=market, objects=objects, source=source)
    return market


async def provision_existing_market_universe(db: AsyncSession, market: Market) -> bool:
    """Backfill legacy catalog markets without making incomplete rows public."""
    objects = await _catalog_objects_for_market(db, market)
    existing_result = await db.execute(
        select(Object)
        .join(MarketObject, MarketObject.object_id == Object.id)
        .where(MarketObject.market_id == market.id)
    )
    existing_objects = existing_result.scalars().all()
    existing_ids = {obj.id for obj in existing_objects}
    catalog_ids = {obj.id for obj in objects}

    has_predictions = bool(
        await db.scalar(select(Prediction.id).where(Prediction.market_id == market.id).limit(1))
    )
    if has_predictions:
        valid = _is_valid_object_set(market, existing_objects)
        if valid:
            await _upsert_universe(db, market=market, objects=existing_objects, source=catalog_source())
            market.status = "open"
        else:
            market.status = "closed"
        return valid

    if not _is_valid_object_set(market, objects):
        market.status = "closed"
        return False

    if existing_ids != catalog_ids:
        await db.execute(delete(MarketObject).where(MarketObject.market_id == market.id))
        db.add_all(MarketObject(market_id=market.id, object_id=obj.id) for obj in objects)
        await db.flush()
    await _upsert_universe(db, market=market, objects=objects, source=catalog_source())
    market.status = "open"
    await db.flush()
    return True
