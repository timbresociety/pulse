"""add Pulse Markets v0 without removing prototype data

Revision ID: 20260722_0001
Revises:
Create Date: 2026-07-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260722_0001"
down_revision = None
branch_labels = None
depends_on = None


def _columns(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _add_missing(table: str, columns: list[sa.Column]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = _columns(inspector, table)
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    _add_missing(
        "users",
        [sa.Column("balance_cents", sa.Integer(), nullable=True, server_default="1000000")],
    )
    op.execute("UPDATE users SET balance_cents = 1000000 WHERE balance_cents IS NULL")
    op.execute("UPDATE users SET pulse_score = 1000 WHERE pulse_score IS NULL OR pulse_score = 0")
    op.alter_column("users", "balance_cents", nullable=False, server_default="1000000")
    op.alter_column("users", "pulse_score", server_default="1000")

    _add_missing(
        "categories",
        [
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("catalog_version", sa.Integer(), nullable=True),
        ],
    )
    _add_missing(
        "markets",
        [
            sa.Column("market_key", sa.String(), nullable=True),
            sa.Column("question", sa.String(), nullable=True),
            sa.Column("context", sa.String(), nullable=True),
            sa.Column("market_kind", sa.String(), nullable=False, server_default="legacy_open_ended"),
            sa.Column("market_version", sa.Integer(), nullable=True),
            sa.Column("simulation_weights_bps", postgresql.JSONB(), nullable=True),
        ],
    )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("markets")}
    if "ix_markets_market_key" not in indexes:
        op.create_index("ix_markets_market_key", "markets", ["market_key"], unique=True)

    if "market_options" not in tables:
        op.create_table(
            "market_options",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("market_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("markets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("option_key", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("display_order", sa.Integer(), nullable=False),
            sa.Column("object_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("objects.id"), nullable=True),
            sa.UniqueConstraint("market_id", "option_key", name="uq_market_option_key"),
            sa.UniqueConstraint("market_id", "display_order", name="uq_market_option_order"),
        )
        op.create_index("ix_market_options_market_id", "market_options", ["market_id"])

    _add_missing(
        "predictions",
        [
            sa.Column("vote_option_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("market_options.id"), nullable=True),
            sa.Column("forecast_bps", postgresql.JSONB(), nullable=True),
            sa.Column("stake_cents", sa.Integer(), nullable=True),
            sa.Column("user_fee_cents", sa.Integer(), nullable=True),
            sa.Column("gross_pool_cents", sa.Integer(), nullable=True),
            sa.Column("net_pool_cents", sa.Integer(), nullable=True),
            sa.Column("actual_distribution_bps", postgresql.JSONB(), nullable=True),
            sa.Column("forecast_error", sa.Float(), nullable=True),
            sa.Column("accuracy_multiplier", sa.Float(), nullable=True),
            sa.Column("accuracy_score", sa.Float(), nullable=True),
            sa.Column("accuracy_percentile", sa.Float(), nullable=True),
            sa.Column("forecast_rank", sa.Integer(), nullable=True),
            sa.Column("total_participants", sa.Integer(), nullable=True),
            sa.Column("payout_cents", sa.Integer(), nullable=True),
            sa.Column("pnl_cents", sa.Integer(), nullable=True),
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payout_credited_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )

    if "balance_transactions" not in tables:
        op.create_table(
            "balance_transactions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("prediction_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("transaction_type", sa.String(), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("balance_after_cents", sa.Integer(), nullable=False),
            sa.Column("reference_key", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("reference_key", name="uq_balance_transaction_reference"),
        )
        op.create_index("ix_balance_transactions_user_id", "balance_transactions", ["user_id"])

    _add_missing(
        "leaderboard_entries",
        [
            sa.Column("avatar_url", sa.String(), nullable=True),
            sa.Column("average_accuracy", sa.Float(), nullable=False, server_default="0"),
            sa.Column("win_rate", sa.Float(), nullable=False, server_default="0"),
            sa.Column("markets_played", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        ],
    )


def downgrade() -> None:
    # Downgrade removes only v0 additions; legacy users, markets and predictions remain.
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "balance_transactions" in tables:
        op.drop_table("balance_transactions")
    prediction_columns = _columns(inspector, "predictions")
    for name in [
        "payout_credited_at", "revealed_at", "settled_at", "pnl_cents", "payout_cents",
        "total_participants", "forecast_rank", "accuracy_percentile", "accuracy_score",
        "accuracy_multiplier", "forecast_error", "actual_distribution_bps", "net_pool_cents",
        "gross_pool_cents", "user_fee_cents", "stake_cents", "forecast_bps", "vote_option_id",
    ]:
        if name in prediction_columns:
            op.drop_column("predictions", name)
    if "market_options" in tables:
        op.drop_table("market_options")
    for name in ["simulation_weights_bps", "market_version", "market_kind", "context", "question", "market_key"]:
        if name in _columns(sa.inspect(op.get_bind()), "markets"):
            op.drop_column("markets", name)
    for name in ["catalog_version", "is_active"]:
        if name in _columns(sa.inspect(op.get_bind()), "categories"):
            op.drop_column("categories", name)
    if "balance_cents" in _columns(sa.inspect(op.get_bind()), "users"):
        op.drop_column("users", "balance_cents")
