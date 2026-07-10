from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, engine
from app.migrations import apply_compatibility_migrations
from app.routers import admin, auth, feed, leaderboard, predictions, users
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_compatibility_migrations(conn)

        # Keep the catalog fast as it grows while preserving deterministic exact matches.
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS objects_category_type_name_idx "
                "ON objects (category_id, object_type, canonical_name)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS object_aliases_lower_alias_idx "
                "ON object_aliases (lower(alias))"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS market_objects_market_object_idx "
                "ON market_objects (market_id, object_id)"
            )
        )

        # Enable trigram fuzzy search; ignore if unavailable.
        try:
            async with conn.begin_nested():
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS objects_canonical_name_trgm_idx "
                        "ON objects USING gin (lower(canonical_name) gin_trgm_ops)"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS object_aliases_alias_trgm_idx "
                        "ON object_aliases USING gin (lower(alias) gin_trgm_ops)"
                    )
                )
        except Exception:
            pass
    await seed_if_empty()
    yield


app = FastAPI(title="Pulse API", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):517[0-9]$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(feed.router)
app.include_router(predictions.router)
app.include_router(leaderboard.router)


@app.get("/health")
async def health():
    return {"status": "ok", "google_auth": settings.google_enabled, "debug": settings.debug}
