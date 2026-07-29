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

    # Keep each serverless instance's pool deliberately small. Managed
    # Postgres providers usually sit behind their own connection pooler, and a
    # large per-instance pool can exhaust the database as Vercel scales out.
    database_pool_size: int = 2
    database_max_overflow: int = 1
    database_pool_timeout_seconds: int = 10
    database_pool_recycle_seconds: int = 300
    database_readiness_timeout_seconds: int = 5

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 43200  # 30 days
    jwt_algorithm: str = "HS256"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    frontend_url: str = "http://localhost:5173"

    debug: bool = True
    # This is intentionally passwordless and unverified. It is for sharing the
    # prototype with testers, not a production authentication system.
    email_login_enabled: bool = True
    # Passwordless email OTP. In production this becomes available only when a
    # Resend API key or SMTP host is configured; DEBUG mode exposes the code in
    # the response so local development does not need an email provider.
    otp_email_enabled: bool = True
    otp_expire_minutes: int = 10
    otp_resend_seconds: int = 60
    otp_max_attempts: int = 5
    otp_pepper: str = ""
    otp_from_email: str = "Pulse <onboarding@resend.dev>"
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False
    # Local and newly provisioned databases need schema initialization. The
    # catalog seed can be disabled independently after a production cutover.
    initialize_database: bool = True
    seed_database: bool = True

    # Pulse Markets v0 game tuning
    reveal_start_seconds: int = 30
    reveal_increment_seconds: int = 30
    starting_balance_cents: int = 1_000_000
    starting_pulse_score: int = 1000

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

    @property
    def otp_signing_secret(self) -> str:
        return self.otp_pepper or self.jwt_secret

    @property
    def otp_delivery_configured(self) -> bool:
        return bool(self.resend_api_key or self.smtp_host)

    @property
    def otp_available(self) -> bool:
        return self.otp_email_enabled and (self.otp_delivery_configured or self.debug)


settings = Settings()
