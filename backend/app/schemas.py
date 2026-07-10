import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


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
    coins: int
    pulse_score: int
    ranked_calls_remaining: int = 10
    categories: list[CategoryOut] = []


class SetCategoriesIn(BaseModel):
    category_ids: list[uuid.UUID]


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


class CreatePredictionIn(BaseModel):
    market_id: uuid.UUID
    object_id: uuid.UUID | None = None
    raw_text: str | None = None


class CreatePredictionOut(BaseModel):
    id: uuid.UUID
    reveal_seconds: int
    new_coins: int | None = None
    entry_cost: int = 10
    is_ranked: bool = True
    ranked_calls_remaining: int = 10
    pool_size: int = 0
    object_id: uuid.UUID | None = None
    canonical_name: str | None = None
    object_type: str | None = None


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


class LeaderboardRow(BaseModel):
    rank: int
    display_name: str
    coins: int
    pulse_score: int
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
