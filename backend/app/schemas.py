import uuid

from pydantic import BaseModel, ConfigDict


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


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
