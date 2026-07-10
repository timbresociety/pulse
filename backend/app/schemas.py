import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    theme: dict | None = None
    sort_order: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    username: str | None
    display_name: str | None
    avatar_url: str | None
    is_admin: bool = False
    coins: int
    pulse_score: int
    ranked_calls_remaining: int = 10
    categories: list[CategoryOut] = []


class SetCategoriesIn(BaseModel):
    category_ids: list[uuid.UUID]


class SetUsernameIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_" for char in normalized):
            raise ValueError("Use 3-32 lowercase letters, numbers, or underscores.")
        return normalized


class EmailLoginStartIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        email = value.strip().casefold()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("Enter a valid email address.")
        return email


class EmailLoginVerifyIn(EmailLoginStartIn):
    code: str = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Enter the six-digit code.")
        return value


class ObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    canonical_name: str
    object_type: str


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    prompt: str
    object_type: str
    category_id: uuid.UUID
    category_name: str | None = None
    category_slug: str | None = None
    category_theme: dict | None = None
    closes_at: datetime | None = None
    participant_count: int = 0
    potential_coin_payout: int = 0
    settle_seconds: int = 0
    entry_cost: int = 10
    pool_size: int = 0
    net_pool: int = 0
    total_call_count: int = 0
    closes_in_seconds: int = 0
    opens_in_batch_seconds: int = 0
    potential_payout_min: int = 0
    potential_payout_max: int = 0
    settlement_type: str = "top_call"
    is_ranked: bool = True


class CreatePredictionIn(BaseModel):
    market_id: uuid.UUID
    object_id: uuid.UUID | None = None
    raw_text: str | None = None


class CreatePredictionOut(BaseModel):
    id: uuid.UUID
    reveal_seconds: int
    new_coins: int
    entry_cost: int
    is_ranked: bool
    ranked_calls_remaining: int
    pool_size: int
    object_id: uuid.UUID
    canonical_name: str
    object_type: str


class MarketUniverseItemIn(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("canonical_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Object names cannot be blank.")
        return cleaned


class CreateMarketIn(BaseModel):
    prompt: str = Field(min_length=8, max_length=300)
    category_id: uuid.UUID
    object_type: str = Field(min_length=2, max_length=80)
    closes_in_minutes: int = Field(ge=5, le=10_080)
    source_name: str = Field(min_length=2, max_length=160)
    source_url: str = Field(min_length=10, max_length=2_000)
    source_updated_at: date
    scope_statement: str = Field(min_length=20, max_length=1_000)
    coverage_statement: str = Field(min_length=20, max_length=1_000)
    objects: list[MarketUniverseItemIn] = Field(min_length=3, max_length=10_000)

    @field_validator("object_type")
    @classmethod
    def clean_object_type(cls, value: str) -> str:
        normalized = value.strip().casefold().replace(" ", "_")
        if not normalized.replace("_", "").isalnum():
            raise ValueError("Object type must contain letters, numbers, or underscores.")
        return normalized

    @field_validator("source_url")
    @classmethod
    def valid_source_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not (cleaned.startswith("https://") or cleaned.startswith("http://")):
            raise ValueError("A source URL must start with http:// or https://.")
        return cleaned


class MarketUniverseOut(BaseModel):
    source_name: str
    source_url: str
    scope_statement: str
    coverage_statement: str
    source_updated_at: datetime
    object_count: int


class AdminMarketOut(BaseModel):
    id: uuid.UUID
    prompt: str
    object_type: str
    category_id: uuid.UUID
    status: str
    closes_at: datetime | None
    universe: MarketUniverseOut


class RevealOut(BaseModel):
    prediction_id: uuid.UUID
    outcome: str
    your_pick: str | None
    winning_object: str | None
    shown_share: float
    coins_won: int
    pulse_delta: int
    new_coins: int
    new_pulse: int
    entry_cost: int = 10
    payout_multiplier: float = 0
    pool_size: int = 0
    settlement_type: str = "top_call"
    taste_signal: str | None = None


class LeaderboardRow(BaseModel):
    rank: int
    display_name: str
    coins: int
    pulse_score: int
    category: str | None = None
    badge: str | None = None
    is_you: bool = False


class HistoryPredictionOut(BaseModel):
    id: uuid.UUID
    market_id: uuid.UUID
    prompt: str
    category_name: str | None = None
    category_slug: str | None = None
    picked_name: str | None = None
    outcome: str | None = None
    locked_at: datetime
    resolved_at: datetime | None = None
    reveal_seconds: int
    shown_share: float | None = None
    coins_won: int
    pulse_delta: int
    entry_cost: int = 10
    payout_multiplier: float = 0
    pool_size: int = 0
    settlement_type: str = "top_call"


class ProfileStatsOut(BaseModel):
    entered: int
    resolved: int
    pending: int
    wins: int
    losses: int
    win_rate: float
    total_coins_won: int
    total_pulse_delta: int
    best_coin_win: int
    avg_crowd_share: float
    ranked_calls_remaining: int = 10
    current_streak: int = 0
    biggest_multiplier: float = 0
    contrarian_wins: int = 0
    early_calls: int = 0
    best_category: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
