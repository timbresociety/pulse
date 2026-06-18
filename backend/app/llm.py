"""On-the-fly market (question) generation via the Anthropic API (Claude).

Generates fresh cultural prompts for a category, constrained to the object_types
that category actually has seeded objects for — so the fuzzy search always has
real answers to match. Degrades gracefully (no-op) when no API key is set.
"""
import json
import logging

from anthropic import AsyncAnthropic
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.models import Category, Market, Object

log = logging.getLogger("pulse.llm")

_client: AsyncAnthropic | None = None
# Categories currently being generated for, to avoid overlapping top-ups.
_in_flight: set[str] = set()


def _get_client() -> AsyncAnthropic | None:
    global _client
    if not settings.llm_enabled:
        return None
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def _category_object_types(db: AsyncSession, category_id) -> list[str]:
    result = await db.execute(
        select(distinct(Object.object_type)).where(
            Object.category_id == category_id, Object.status == "active"
        )
    )
    return [row[0] for row in result.all()]


async def _existing_prompts(db: AsyncSession, category_id) -> list[str]:
    result = await db.execute(select(Market.prompt).where(Market.category_id == category_id))
    return [row[0] for row in result.all()]


def _build_prompt(category_name: str, object_types: list[str], existing: list[str], n: int) -> str:
    existing_block = "\n".join(f"- {p}" for p in existing[:40]) or "(none yet)"
    return f"""You generate punchy, divisive cultural "prediction" market questions for a \
swipe game called Pulse. Category: {category_name}.

Each question asks players to predict what the crowd will pick. Good prompts are \
short, opinionated, and spark debate (e.g. "Most overrated artist?", "Best \
late-night song?", "Hardest anime character?"). Avoid yes/no questions and avoid \
anything political, hateful, or about private individuals.

Each question must target exactly one object_type, chosen ONLY from this list: \
{object_types}. (The game already has answer options of these types for this category.)

Do NOT repeat or lightly reword any of these existing questions:
{existing_block}

Generate {n} fresh, distinct questions."""


_SCHEMA = {
    "type": "object",
    "properties": {
        "markets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "object_type": {"type": "string"},
                },
                "required": ["prompt", "object_type"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["markets"],
    "additionalProperties": False,
}


async def generate_markets_for_category(category_id) -> int:
    """Generate and insert a batch of markets for one category. Returns count added."""
    client = _get_client()
    if client is None:
        return 0

    key = str(category_id)
    if key in _in_flight:
        return 0
    _in_flight.add(key)
    try:
        async with SessionLocal() as db:
            category = await db.get(Category, category_id)
            if category is None:
                return 0
            object_types = await _category_object_types(db, category_id)
            if not object_types:
                return 0
            existing = await _existing_prompts(db, category_id)

            prompt = _build_prompt(
                category.name, object_types, existing, settings.feed_topup_batch
            )
            resp = await client.messages.create(
                model=settings.llm_model,
                max_tokens=2000,
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "{}")
            data = json.loads(text)

            valid_types = set(object_types)
            seen = {p.lower() for p in existing}
            added = 0
            for m in data.get("markets", []):
                ptext = (m.get("prompt") or "").strip()
                otype = (m.get("object_type") or "").strip()
                if not ptext or otype not in valid_types:
                    continue
                if ptext.lower() in seen:
                    continue
                seen.add(ptext.lower())
                db.add(
                    Market(
                        prompt=ptext,
                        category_id=category_id,
                        object_type=otype,
                        status="open",
                    )
                )
                added += 1
            await db.commit()
            log.info("Generated %d markets for category %s", added, category.slug)
            return added
    except Exception as e:  # never let generation break the request path
        log.warning("Market generation failed for %s: %s", category_id, e)
        return 0
    finally:
        _in_flight.discard(key)
