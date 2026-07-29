import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import Base, engine
from app.migrations import upgrade_database
from app.routers import auth, debug, feed, leaderboard, predictions, users
from app.seed import seed_if_empty

API_PREFIX = "/api"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.initialize_database:
        async with engine.begin() as conn:
            # Enable trigram fuzzy search; ignore if unavailable.
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            except Exception:
                pass
            await conn.run_sync(Base.metadata.create_all)
        # create_all makes fresh databases convenient; Alembic performs the
        # additive ALTERs required by existing prototype databases.
        await asyncio.to_thread(upgrade_database)
    # Catalog upserts are idempotent and advisory-lock protected. Disable them
    # after production has been seeded so serverless cold starts stay read-only.
    if settings.seed_database:
        await seed_if_empty()
    yield


app = FastAPI(
    title="Pulse Demo API",
    lifespan=lifespan,
    docs_url=f"{API_PREFIX}/docs",
    openapi_url=f"{API_PREFIX}/openapi.json",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.jwt_secret,
    https_only=not settings.debug,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(feed.router, prefix=API_PREFIX)
app.include_router(predictions.router, prefix=API_PREFIX)
app.include_router(leaderboard.router, prefix=API_PREFIX)
app.include_router(debug.router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", response_class=JSONResponse)
async def health():
    """Liveness check that never depends on the database."""
    return JSONResponse(
        {
            "status": "ok",
            "email_login": settings.email_login_enabled,
            "email_otp": settings.otp_available,
            "google_auth": settings.google_enabled,
            "debug": settings.debug,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get(f"{API_PREFIX}/ready", response_class=JSONResponse)
async def readiness():
    """Readiness check that verifies the database is reachable."""
    try:
        async with asyncio.timeout(settings.database_readiness_timeout_seconds):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database readiness check failed")
        return JSONResponse(
            {"status": "unavailable"},
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    return JSONResponse(
        {"status": "ready"},
        headers={"Cache-Control": "no-store"},
    )
