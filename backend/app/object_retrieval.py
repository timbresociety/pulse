from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Market, MarketObject, Object, ObjectAlias

STOP_WORDS = {"a", "an", "and", "by", "for", "in", "of", "on", "the", "to"}


def normalize(value: str) -> str:
    return " ".join("".join(char if char.isalnum() else " " for char in value.casefold()).split())


def _tokens(value: str) -> list[str]:
    tokens = value.split()
    meaningful_tokens = [token for token in tokens if token not in STOP_WORDS]
    return meaningful_tokens or tokens


def _score_name(term: str, names: list[str]) -> float:
    term_tokens = _tokens(term)
    term_token_set = set(term_tokens)
    compact_term = term.replace(" ", "")
    best = 0.0

    for raw_name in names:
        name = normalize(raw_name)
        if not name:
            continue
        name_tokens = _tokens(name)
        name_token_set = set(name_tokens)
        compact_name = name.replace(" ", "")
        ratio = max(
            SequenceMatcher(None, term, name).ratio(),
            SequenceMatcher(None, compact_term, compact_name).ratio(),
        )
        exact_hits = len(term_token_set & name_token_set)
        prefix_hits = sum(
            any(name_token.startswith(token) or token.startswith(name_token) for name_token in name_tokens)
            for token in term_tokens
        )
        coverage = max(exact_hits, prefix_hits) / max(1, len(term_tokens))
        overlap = exact_hits / max(1, len(term_token_set | name_token_set))
        score = ratio * 52 + coverage * 44 + overlap * 24

        if name == term or compact_name == compact_term:
            score += 92
        elif name.startswith(term) or compact_name.startswith(compact_term):
            score += 62
        elif term in name or compact_term in compact_name:
            score += 54

        if len(term) <= 3 and not (
            name.startswith(term)
            or compact_name.startswith(compact_term)
            or any(token.startswith(term) for token in name_tokens)
        ):
            score *= 0.45
        best = max(best, score)
    return best


def _matches_short_query(term: str, names: list[str]) -> bool:
    if len(term) > 4:
        return True
    compact_term = term.replace(" ", "")
    return any(
        (name := normalize(raw_name)).startswith(term)
        or name.replace(" ", "").startswith(compact_term)
        or any(token.startswith(term) for token in name.split())
        for raw_name in names
    )


def _minimum_score(term: str) -> int:
    if len(term) <= 3:
        return 72
    if len(term) <= 7:
        return 58
    return 44


def _is_prefix_match(term: str, names: list[str]) -> bool:
    compact_term = term.replace(" ", "")
    return any(
        (name := normalize(raw_name)) == term
        or name.replace(" ", "") == compact_term
        or name.startswith(term)
        or name.replace(" ", "").startswith(compact_term)
        for raw_name in names
    )


async def _scoped_candidates(
    db: AsyncSession,
    market: Market,
    term: str,
) -> list[tuple[float, Object, list[str]]]:
    result = await db.execute(
        select(Object, ObjectAlias.alias)
        .join(MarketObject, MarketObject.object_id == Object.id)
        .outerjoin(ObjectAlias, ObjectAlias.object_id == Object.id)
        .where(
            MarketObject.market_id == market.id,
            Object.status == "active",
            Object.category_id == market.category_id,
            Object.object_type == market.object_type,
        )
    )

    grouped: dict[object, tuple[Object, list[str]]] = {}
    for obj, alias in result.all():
        if obj.id not in grouped:
            grouped[obj.id] = (obj, [obj.canonical_name])
        if alias:
            grouped[obj.id][1].append(alias)

    strict: list[tuple[float, Object, list[str]]] = []
    fuzzy: list[tuple[float, Object, list[str]]] = []
    for obj, names in grouped.values():
        if not _matches_short_query(term, names):
            continue
        score = _score_name(term, names)
        if score < _minimum_score(term):
            continue
        candidate = (score, obj, names)
        if _is_prefix_match(term, names):
            strict.append(candidate)
        else:
            fuzzy.append(candidate)
    return strict or fuzzy


async def search_market_objects(
    db: AsyncSession,
    market: Market,
    category: Category,
    raw_query: str,
    limit: int,
) -> list[Object]:
    if market.category_id != category.id:
        return []
    term = normalize(raw_query)
    if not term:
        return []

    candidates = await _scoped_candidates(db, market, term)
    candidates.sort(key=lambda item: (-item[0], item[1].canonical_name.casefold()))
    return [obj for _score, obj, _names in candidates[:limit]]


async def resolve_market_object(
    db: AsyncSession,
    market: Market,
    category: Category,
    raw_query: str,
) -> Object | None:
    term = normalize(raw_query)
    if not term:
        return None

    candidates = await _scoped_candidates(db, market, term)
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].canonical_name.casefold()))

    for _score, obj, names in candidates:
        if any(normalize(name) == term for name in names):
            return obj

    best_score, best, _names = candidates[0]
    return best if best_score >= 116 else None
