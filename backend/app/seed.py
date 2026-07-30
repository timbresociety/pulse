"""Idempotent Pulse Markets v0 catalog migration and seed."""

import json
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.game import PULSE_MARKET_KIND
from app.leaderboard_data import CURATED_BOT_DATA
from app.models import Category, LeaderboardEntry, Market, MarketOption, Prediction, User

CATALOG_PATH = Path(__file__).parent / "data" / "pulse_markets_v0.json"
SEED_LOCK_ID = 1_345_391_699

def load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def validate_catalog(catalog: dict) -> None:
    version = catalog.get("version")
    markets = catalog.get("markets", [])
    category_slugs = {category["slug"] for category in catalog.get("categories", [])}
    if not isinstance(version, int):
        raise ValueError("Catalog version must be an integer")
    seen_market_keys: set[str] = set()
    counts = {slug: 0 for slug in category_slugs}
    for market in markets:
        key = market["key"]
        if key in seen_market_keys:
            raise ValueError(f"Duplicate market key: {key}")
        seen_market_keys.add(key)
        if market["category_slug"] not in category_slugs:
            raise ValueError(f"Unknown category for {key}")
        options = market["options"]
        weights = market["simulation_weights_bps"]
        if not 4 <= len(options) <= 8:
            raise ValueError(f"{key} must have four to eight options")
        if len(options) != len(weights) or any(not isinstance(weight, int) for weight in weights):
            raise ValueError(f"{key} has invalid simulation weights")
        if sum(weights) != 10_000:
            raise ValueError(f"{key} simulation weights must total 10,000")
        option_keys = [option["key"] for option in options]
        labels = [option["label"].casefold() for option in options]
        if len(option_keys) != len(set(option_keys)):
            raise ValueError(f"{key} has duplicate option keys")
        if len(labels) != len(set(labels)):
            raise ValueError(f"{key} has duplicate option labels")
        counts[market["category_slug"]] += 1
    if any(count < 8 for count in counts.values()):
        raise ValueError("Every active category requires at least eight markets")


async def seed_if_empty() -> None:
    """Compatibility name: the operation now safely runs on every startup."""
    async with SessionLocal() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": SEED_LOCK_ID})
        await seed_catalog(db)


async def seed_catalog(db: AsyncSession) -> None:
    catalog = load_catalog()
    validate_catalog(catalog)
    version = catalog["version"]

    existing_categories = {
        category.slug: category
        for category in (await db.execute(select(Category))).scalars().all()
    }
    for category in existing_categories.values():
        category.is_active = False

    active_categories: dict[str, Category] = {}
    for sort_order, entry in enumerate(catalog["categories"]):
        category = existing_categories.get(entry["slug"])
        if category is None:
            category = Category(slug=entry["slug"], name=entry["name"])
            db.add(category)
        category.name = entry["name"]
        category.sort_order = sort_order
        category.theme = {"color": entry["color"]}
        category.is_active = True
        category.catalog_version = version
        active_categories[entry["slug"]] = category
    await db.flush()

    # Old open-ended questions remain queryable for history/search compatibility,
    # but are never eligible for the v0 feed.
    legacy_markets = (
        await db.execute(select(Market).where(Market.market_kind != PULSE_MARKET_KIND))
    ).scalars().all()
    for market in legacy_markets:
        market.status = "legacy"
        market.market_kind = market.market_kind or "legacy_open_ended"

    existing_v0 = {
        market.market_key: market
        for market in (
            await db.execute(select(Market).where(Market.market_key.is_not(None)))
        ).scalars().all()
    }

    for entry in catalog["markets"]:
        market = existing_v0.get(entry["key"])
        if market is None:
            market = Market(
                market_key=entry["key"],
                prompt=entry["question"],
                question=entry["question"],
                context=entry.get("context"),
                category_id=active_categories[entry["category_slug"]].id,
                object_type="poll_option",
                market_kind=PULSE_MARKET_KIND,
                market_version=version,
                status="active",
                simulation_weights_bps=entry["simulation_weights_bps"],
            )
            db.add(market)
            await db.flush()

        participation_exists = bool(
            await db.scalar(select(Prediction.id).where(Prediction.market_id == market.id).limit(1))
        )
        if not participation_exists:
            market.prompt = entry["question"]
            market.question = entry["question"]
            market.context = entry.get("context")
            market.category_id = active_categories[entry["category_slug"]].id
            market.object_type = "poll_option"
            market.market_kind = PULSE_MARKET_KIND
            market.market_version = version
            market.status = "active"
            market.simulation_weights_bps = entry["simulation_weights_bps"]

            existing_options = {
                option.option_key: option
                for option in (
                    await db.execute(select(MarketOption).where(MarketOption.market_id == market.id))
                ).scalars().all()
            }
            # Move existing rows out of the positive display-order range first,
            # so a future catalog reorder cannot trip the unique order constraint.
            for temporary_order, option in enumerate(existing_options.values(), start=1):
                option.display_order = -temporary_order
            if existing_options:
                await db.flush()
            catalog_keys = {option["key"] for option in entry["options"]}
            for old_key, old_option in existing_options.items():
                if old_key not in catalog_keys:
                    await db.delete(old_option)
            for display_order, option_entry in enumerate(entry["options"]):
                option = existing_options.get(option_entry["key"])
                if option is None:
                    option = MarketOption(
                        market_id=market.id,
                        option_key=option_entry["key"],
                        label=option_entry["label"],
                        display_order=display_order,
                    )
                    db.add(option)
                else:
                    option.label = option_entry["label"]
                    option.display_order = display_order

    # Stable bot profiles are updated in place by display name.
    bot_rows = (await db.execute(select(LeaderboardEntry))).scalars().all()
    bots_by_name = {bot.display_name: bot for bot in bot_rows}
    for name, pulse, accuracy, win_rate, played, streak in CURATED_BOT_DATA:
        bot = bots_by_name.get(name)
        if bot is None:
            bot = LeaderboardEntry(display_name=name, is_bot=True)
            db.add(bot)
        bot.pulse_score = pulse
        bot.average_accuracy = accuracy
        bot.win_rate = win_rate
        bot.markets_played = played
        bot.current_streak = streak

    active_ids = {category.id for category in active_categories.values()}
    users = (await db.execute(select(User))).scalars().all()
    for user in users:
        if user.balance_cents is None:
            user.balance_cents = 1_000_000
        if not user.pulse_score:
            user.pulse_score = 1000
        if not any(category.id in active_ids for category in user.categories):
            user.categories = list(active_categories.values())

    await db.commit()
