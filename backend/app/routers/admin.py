"""Administrator-only market creation.

No endpoint can create a market from a prompt alone: a scoped source, freshness
date, coverage statement, and a mutually-exclusive object list are required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_admin
from app.database import get_db
from app.market_universe import UniverseSource, create_market_with_universe
from app.models import Category, Object, ObjectAlias, User
from app.object_retrieval import normalize
from app.schemas import AdminMarketOut, CreateMarketIn, MarketUniverseOut, ObjectOut

router = APIRouter(prefix="/admin", tags=["admin"])


def _assert_mece_items(payload: CreateMarketIn) -> None:
    """Check the part of MECE that can be proven mechanically.

    Completeness is asserted against the cited source in `coverage_statement`.
    Exclusivity is enforced by rejecting canonical-name and alias collisions.
    """
    seen: dict[str, str] = {}
    canonical_keys: set[str] = set()
    for item in payload.objects:
        canonical_key = normalize(item.canonical_name)
        if canonical_key in canonical_keys:
            raise HTTPException(422, "Each canonical object may appear only once.")
        canonical_keys.add(canonical_key)
        for raw in [item.canonical_name, *item.aliases]:
            key = normalize(raw)
            if not key:
                raise HTTPException(422, "Object names and aliases cannot be blank.")
            prior = seen.get(key)
            if prior is not None and prior != item.canonical_name:
                raise HTTPException(
                    422,
                    f"'{raw}' appears in more than one object; the universe must be mutually exclusive.",
                )
            seen[key] = item.canonical_name


async def _add_missing_aliases(
    db: AsyncSession,
    *,
    obj: Object,
    category_id,
    object_type: str,
    aliases: list[str],
) -> None:
    existing_result = await db.execute(
        select(ObjectAlias.alias).where(ObjectAlias.object_id == obj.id)
    )
    existing = {normalize(alias) for alias in existing_result.scalars()}
    for raw_alias in aliases:
        alias = " ".join(raw_alias.split())
        key = normalize(alias)
        if not key or key in existing:
            continue
        collision = await db.scalar(
            select(ObjectAlias.id)
            .join(Object, Object.id == ObjectAlias.object_id)
            .where(
                Object.category_id == category_id,
                Object.object_type == object_type,
                func.lower(ObjectAlias.alias) == alias.casefold(),
                Object.id != obj.id,
            )
            .limit(1)
        )
        if collision is not None:
            raise HTTPException(
                422,
                f"Alias '{alias}' already identifies another object in this universe scope.",
            )
        db.add(ObjectAlias(object_id=obj.id, alias=alias))
        existing.add(key)


@router.post("/markets", response_model=AdminMarketOut, status_code=201)
async def create_market(
    payload: CreateMarketIn,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _assert_mece_items(payload)
    category = await db.get(Category, payload.category_id)
    if category is None:
        raise HTTPException(404, "Category not found")

    objects: list[Object] = []
    for item in payload.objects:
        canonical_name = " ".join(item.canonical_name.split())
        obj = await db.scalar(
            select(Object)
            .where(
                Object.category_id == category.id,
                Object.object_type == payload.object_type,
                func.lower(Object.canonical_name) == canonical_name.casefold(),
            )
            .limit(1)
        )
        if obj is None:
            obj = Object(
                canonical_name=canonical_name,
                object_type=payload.object_type,
                category_id=category.id,
                object_metadata={
                    "source_name": payload.source_name,
                    "source_url": payload.source_url,
                    "scope_statement": payload.scope_statement,
                },
                status="active",
            )
            db.add(obj)
            await db.flush()
        else:
            obj.status = "active"
        await _add_missing_aliases(
            db,
            obj=obj,
            category_id=category.id,
            object_type=payload.object_type,
            aliases=[obj.canonical_name, *item.aliases],
        )
        objects.append(obj)

    source_updated_at = datetime.combine(payload.source_updated_at, time.min, tzinfo=timezone.utc)
    market = await create_market_with_universe(
        db,
        prompt=payload.prompt,
        category_id=category.id,
        object_type=payload.object_type,
        object_ids=[obj.id for obj in objects],
        source=UniverseSource(
            source_name=payload.source_name,
            source_url=payload.source_url,
            scope_statement=payload.scope_statement,
            coverage_statement=payload.coverage_statement,
            source_updated_at=source_updated_at,
            created_by_user_id=admin.id,
        ),
        closes_at=datetime.now(timezone.utc) + timedelta(minutes=payload.closes_in_minutes),
    )
    if market is None:
        await db.rollback()
        raise HTTPException(422, "The supplied object list is not valid for this market.")
    await db.commit()
    await db.refresh(market)

    return AdminMarketOut(
        id=market.id,
        prompt=market.prompt,
        object_type=market.object_type,
        category_id=market.category_id,
        status=market.status,
        closes_at=market.closes_at,
        universe=MarketUniverseOut(
            source_name=payload.source_name,
            source_url=payload.source_url,
            scope_statement=payload.scope_statement,
            coverage_statement=payload.coverage_statement,
            source_updated_at=source_updated_at,
            object_count=len(objects),
        ),
    )


@router.get("/catalog", response_model=list[ObjectOut])
async def catalog(
    category_id: uuid.UUID,
    object_type: str,
    q: str = "",
    limit: int = 50,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Review existing canonical objects while composing a source universe."""
    limit = min(max(limit, 1), 100)
    statement = select(Object).where(
        Object.category_id == category_id,
        Object.object_type == object_type.casefold(),
        Object.status == "active",
    )
    if q.strip():
        statement = statement.where(func.lower(Object.canonical_name).like(f"%{q.strip().casefold()}%"))
    result = await db.execute(statement.order_by(Object.canonical_name).limit(limit))
    return result.scalars().all()
