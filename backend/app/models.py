import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


user_category = Table(
    "user_category",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # Retained for legacy prototype rows. Pulse Markets v0 uses integer USD cents.
    coins: Mapped[int] = mapped_column(Integer, default=0)
    balance_cents: Mapped[int] = mapped_column(Integer, default=1_000_000, server_default="1000000")
    pulse_score: Mapped[int] = mapped_column(Integer, default=1000, server_default="1000")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    categories: Mapped[list["Category"]] = relationship(secondary=user_category, lazy="selectin")


class EmailOtpChallenge(Base):
    __tablename__ = "email_otp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), index=True)
    code_digest: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    theme: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    catalog_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Object(Base):
    __tablename__ = "objects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    canonical_name: Mapped[str] = mapped_column(String, index=True)
    object_type: Mapped[str] = mapped_column(String, index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"))
    object_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")


class ObjectAlias(Base):
    __tablename__ = "object_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("objects.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String, index=True)


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    # Legacy columns remain populated so existing rows and old predictions survive.
    prompt: Mapped[str] = mapped_column(String)
    object_type: Mapped[str] = mapped_column(String)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"))
    status: Mapped[str] = mapped_column(String, default="legacy")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    market_key: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    question: Mapped[str | None] = mapped_column(String, nullable=True)
    context: Mapped[str | None] = mapped_column(String, nullable=True)
    market_kind: Mapped[str] = mapped_column(String, default="legacy_open_ended", server_default="legacy_open_ended")
    market_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Backend-only authored population mean. Never serialize this column in a public schema.
    simulation_weights_bps: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)

    options: Mapped[list["MarketOption"]] = relationship(
        back_populates="market", lazy="selectin", order_by="MarketOption.display_order"
    )


class MarketOption(Base):
    __tablename__ = "market_options"
    __table_args__ = (
        UniqueConstraint("market_id", "option_key", name="uq_market_option_key"),
        UniqueConstraint("market_id", "display_order", name="uq_market_option_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("markets.id", ondelete="CASCADE"), index=True
    )
    option_key: Mapped[str] = mapped_column(String)
    label: Mapped[str] = mapped_column(String)
    display_order: Mapped[int] = mapped_column(Integer)
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("objects.id"), nullable=True)

    market: Mapped[Market] = relationship(back_populates="options")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("user_id", "market_id", name="uq_user_market"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    market_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("markets.id"), index=True)

    # Legacy open-ended answer/result fields are intentionally retained.
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("objects.id"), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shown_winner_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("objects.id"), nullable=True)
    shown_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    coins_won: Mapped[int] = mapped_column(Integer, default=0)

    vote_option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_options.id"), nullable=True
    )
    forecast_bps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stake_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reveal_seconds: Mapped[int] = mapped_column(Integer)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    gross_pool_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    net_pool_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_distribution_bps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    forecast_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_multiplier: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payout_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pnl_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pulse_delta: Mapped[int] = mapped_column(Integer, default=0)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payout_credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"
    __table_args__ = (UniqueConstraint("reference_key", name="uq_balance_transaction_reference"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True
    )
    transaction_type: Mapped[str] = mapped_column(String)
    amount_cents: Mapped[int] = mapped_column(Integer)
    balance_after_cents: Mapped[int] = mapped_column(Integer)
    reference_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LeaderboardEntry(Base):
    __tablename__ = "leaderboard_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    display_name: Mapped[str] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    coins: Mapped[int] = mapped_column(Integer, default=0)
    pulse_score: Mapped[int] = mapped_column(Integer, default=1000)
    average_accuracy: Mapped[float] = mapped_column(Float, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0)
    markets_played: Mapped[int] = mapped_column(Integer, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=True)
