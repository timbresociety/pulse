"""Small, idempotent compatibility migrations for the managed Postgres database.

The project predates a migration runner.  These statements keep already-created
cloud databases compatible while `Base.metadata.create_all()` handles fresh
instances.  They are deliberately additive and safe to run on every deploy.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_compatibility_migrations(conn: AsyncConnection) -> None:
    await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(32)"))
    await conn.execute(
        text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE")
    )
    await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS opens_at TIMESTAMPTZ"))
    await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS closes_at TIMESTAMPTZ"))
    await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS settled_at TIMESTAMPTZ"))
    await conn.execute(text("ALTER TABLE markets ADD COLUMN IF NOT EXISTS winning_object_id UUID"))
    await conn.execute(
        text(
            "UPDATE markets SET opens_at = COALESCE(opens_at, created_at, NOW()) "
            "WHERE opens_at IS NULL"
        )
    )
    # Existing open markets receive a real close time. New market creation
    # always supplies this value explicitly.
    await conn.execute(
        text(
            "UPDATE markets SET closes_at = NOW() + INTERVAL '24 hours' "
            "WHERE status = 'open' AND closes_at IS NULL"
        )
    )
    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_unique "
            "ON users (lower(username)) WHERE username IS NOT NULL"
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS markets_open_close_idx ON markets (status, closes_at)")
    )
