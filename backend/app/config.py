from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse"

    @field_validator("database_url")
    @classmethod
    def use_asyncpg_driver(cls, value: str) -> str:
        """Accept the standard Postgres URLs supplied by managed providers."""
        if value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        elif value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgres://")

        # Neon appends libpq-specific query parameters. asyncpg uses `ssl`
        # instead of `sslmode` and does not accept `channel_binding`.
        parsed = urlsplit(value)
        query = [
            ("ssl" if key == "sslmode" else key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key != "channel_binding"
        ]
        return urlunsplit(parsed._replace(query=urlencode(query)))

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 43200  # 30 days
    jwt_algorithm: str = "HS256"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    frontend_url: str = "http://localhost:5173"

    debug: bool = True
    # This is intentionally passwordless and unverified. It is for sharing the
    # prototype with testers, not a production authentication system.
    email_login_enabled: bool = True
    # Local and newly provisioned databases need the schema and seed. Once a
    # production database is ready, disabling this removes cold-start DDL work.
    initialize_database: bool = True

    # Game tuning
    reveal_start_seconds: int = 30
    reveal_increment_seconds: int = 30
    win_probability: float = 0.65
    no_back_to_back_loss_window: int = 5
    first_market_always_win: bool = True
    starting_coins: int = 100
    base_coin_payout: int = 50
    leaderboard_rank_metric: str = "coins"  # "coins" | "pulse"

    # LLM market generation
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"
    feed_topup_threshold: int = 8
    feed_topup_batch: int = 10

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
