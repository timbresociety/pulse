import re
import uuid
from datetime import datetime

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
    display_name: str | None
    avatar_url: str | None
    balance_cents: int
    pulse_score: int
    categories: list[CategoryOut] = []


class SetCategoriesIn(BaseModel):
    category_ids: list[uuid.UUID]


class ObjectOut(BaseModel):
    """Legacy search compatibility only; v0 participation never accepts this shape."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    canonical_name: str
    object_type: str


class MarketCategoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class MarketOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    key: str
    label: str
    display_order: int


class MarketOut(BaseModel):
    id: uuid.UUID
    key: str
    question: str
    context: str | None = None
    category: MarketCategoryOut
    options: list[MarketOptionOut]
    participant_count: int
    pool_volume_cents: int
    net_pool_volume_cents: int = 0
    reveal_seconds: int
    avatars: list[str]
    # Populated only when DEBUG=true.
    simulation_seed: str | None = None
    latent_distribution_bps: dict[str, int] | None = None


class CreatePredictionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_id: uuid.UUID
    vote_option_id: uuid.UUID
    forecast_bps: dict[uuid.UUID, int]
    stake_cents: int = Field(gt=0)

    @field_validator("forecast_bps")
    @classmethod
    def validate_allocations(cls, value: dict[uuid.UUID, int]) -> dict[uuid.UUID, int]:
        if any(allocation < 0 or allocation > 10_000 for allocation in value.values()):
            raise ValueError("Forecast allocations must be between 0 and 10,000 basis points")
        return value


class CreatePredictionOut(BaseModel):
    id: uuid.UUID
    reveal_seconds: int
    locked_at: datetime
    stake_cents: int
    user_fee_cents: int
    new_balance_cents: int


class DistributionPointOut(BaseModel):
    option_id: uuid.UUID
    key: str
    label: str
    bps: int


class DifferenceOut(BaseModel):
    option_id: uuid.UUID
    label: str
    forecast_bps: int
    actual_bps: int
    difference_bps: int


class RevealOut(BaseModel):
    prediction_id: uuid.UUID
    market_id: uuid.UUID
    question: str
    category_name: str
    vote: MarketOptionOut
    forecast: list[DistributionPointOut]
    actual_distribution: list[DistributionPointOut]
    largest_differences: list[DifferenceOut]
    accuracy_score: float
    accuracy_percentile: float
    forecast_rank: int
    total_participants: int
    crowd_median_accuracy_score: float
    crowd_top_quartile_accuracy_score: float
    crowd_top_ten_accuracy_score: float
    break_even_accuracy_score: float
    accuracy_weighted_stake_cents: float
    weighted_pool_share: float
    stake_cents: int
    user_fee_cents: int
    gross_pool_cents: int
    net_pool_cents: int
    payout_cents: int
    pnl_cents: int
    pulse_delta: int
    new_balance_cents: int
    new_pulse_score: int
    revealed_at: datetime


class HistoryPredictionOut(BaseModel):
    id: uuid.UUID
    market_id: uuid.UUID
    question: str
    category_name: str
    category_slug: str
    status: str
    vote: MarketOptionOut
    forecast: list[DistributionPointOut]
    actual_distribution: list[DistributionPointOut] | None = None
    locked_at: datetime
    reveal_seconds: int
    reveal_at: datetime
    seconds_remaining: int
    participant_count: int
    pool_volume_cents: int
    stake_cents: int
    user_fee_cents: int
    accuracy_score: float | None = None
    accuracy_percentile: float | None = None
    forecast_rank: int | None = None
    total_participants: int | None = None
    payout_cents: int | None = None
    pnl_cents: int | None = None
    pulse_delta: int | None = None
    revealed_at: datetime | None = None


class WalletTransactionOut(BaseModel):
    id: uuid.UUID
    transaction_type: str
    amount_cents: int
    balance_after_cents: int
    prediction_id: uuid.UUID | None = None
    question: str | None = None
    created_at: datetime


class WalletOut(BaseModel):
    available_balance_cents: int
    total_stakes_cents: int
    total_payouts_cents: int
    net_pnl_cents: int
    debug_topup_enabled: bool
    transactions: list[WalletTransactionOut]


class LeaderboardRow(BaseModel):
    rank: int
    display_name: str
    avatar_url: str | None = None
    pulse_score: int
    average_accuracy: float
    win_rate: float
    markets_played: int
    current_streak: int
    is_you: bool = False


class LeaderboardOut(BaseModel):
    total_players: int
    user_rank: int
    rows: list[LeaderboardRow]


class ActivityDayOut(BaseModel):
    date: str
    markets_played: int


class ProfileStatsOut(BaseModel):
    markets_played: int
    revealed: int
    pending: int
    wins: int
    losses: int
    win_rate: float
    average_accuracy: float
    total_pnl_cents: int
    total_volume_cents: int
    biggest_win_cents: int
    current_streak: int
    longest_streak: int
    best_category: str | None = None
    activity: list[ActivityDayOut]


class AppBootstrapOut(BaseModel):
    user: UserOut
    profile_stats: ProfileStatsOut
    wallet: WalletOut
    leaderboard: LeaderboardOut


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EmailLoginOut(TokenOut):
    user: UserOut


class EmailLoginIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().lower()
        if len(email) > 320 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Enter a valid email address")
        return email


class AuthMethodsOut(BaseModel):
    email_otp: bool
    email_login: bool
    google: bool


class EmailOtpRequestOut(BaseModel):
    challenge_id: uuid.UUID
    expires_in_seconds: int
    # Present only in DEBUG mode when no email provider is configured.
    dev_code: str | None = None


class EmailOtpVerifyIn(BaseModel):
    challenge_id: uuid.UUID
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        code = re.sub(r"\s+", "", value)
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError("Enter the 6-digit code")
        return code
