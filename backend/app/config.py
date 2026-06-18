from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://pulse:pulse@localhost:5432/pulse"

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 43200  # 30 days
    jwt_algorithm: str = "HS256"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    frontend_url: str = "http://localhost:5173"

    debug: bool = True

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
