from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
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

    # Passwordless email authentication. Resend is used in production; the
    # console transport exists only for local development and never exposes a
    # code through the public UI.
    email_delivery: str = "resend"  # "resend" | "console"
    resend_api_key: str = ""
    email_from: str = "Pulse <signin@example.com>"
    email_login_ttl_minutes: int = 15
    email_login_max_requests_per_window: int = 5
    admin_emails: str = "luckyloot786@gmail.com"

    frontend_url: str = "http://localhost:5173"
    public_api_url: str = "http://localhost:8000"
    cors_origins: str = ""

    debug: bool = True

    # Market tuning
    default_market_duration_minutes: int = 1440
    starting_coins: int = 100
    leaderboard_rank_metric: str = "coins"  # "coins" | "pulse"

    # LLM market generation stays disabled until a generated market can arrive
    # with an explicit source-bound answer universe.
    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-4-8"
    feed_topup_threshold: int = 8
    feed_topup_batch: int = 10

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not value:
            return value
        url = str(value).strip()
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]

        parsed = urlsplit(url)
        query_items = []
        changed = False
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
            if key == "sslmode":
                query_items.append(("ssl", "require" if item_value else item_value))
                changed = True
            else:
                query_items.append((key, item_value))
        if changed:
            url = urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urlencode(query_items),
                    parsed.fragment,
                )
            )
        return url

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def authorized_admin_emails(self) -> set[str]:
        return {
            email.strip().casefold()
            for email in self.admin_emails.split(",")
            if email.strip()
        }

    @property
    def email_delivery_ready(self) -> bool:
        return self.email_delivery == "console" or bool(self.resend_api_key)

    @property
    def allowed_cors_origins(self) -> list[str]:
        origins = [self.frontend_url]
        origins.extend(origin.strip() for origin in self.cors_origins.split(",") if origin.strip())
        origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
        return list(dict.fromkeys(origin for origin in origins if origin))


settings = Settings()
