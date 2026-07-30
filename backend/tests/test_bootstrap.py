import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.routers.users import _split_bootstrap_rows, bootstrap


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def scalars(self):
        return self


class _BootstrapDb:
    def __init__(self):
        self.results = [_Rows([])]
        self.execute_count = 0

    async def execute(self, _statement):
        result = self.results[self.execute_count]
        self.execute_count += 1
        return result


def test_bootstrap_returns_all_summary_screens_from_shared_rows():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="reader@example.com",
        display_name="Reader",
        avatar_url=None,
        balance_cents=123_456,
        pulse_score=1_023,
        categories=[],
    )
    db = _BootstrapDb()

    response = asyncio.run(bootstrap(user=user, db=db))

    assert db.execute_count == 1
    assert response.user.email == "reader@example.com"
    assert response.profile_stats.markets_played == 0
    assert response.wallet.available_balance_cents == 123_456
    assert response.wallet.transactions == []
    assert response.leaderboard.total_players == 5_201
    assert any(row.is_you for row in response.leaderboard.rows)


def test_compact_bootstrap_rows_restore_prediction_and_transaction_order():
    now = datetime.now(timezone.utc)

    def row(**values):
        return SimpleNamespace(_mapping=values)

    common_prediction = {
        "row_kind": "prediction",
        "category_name": "Internet",
        "stake_cents": 200,
        "payout_cents": None,
        "settled_at": None,
        "revealed_at": None,
        "pnl_cents": None,
        "accuracy_score": None,
        "transaction_type": None,
        "amount_cents": None,
        "balance_after_cents": None,
        "transaction_prediction_id": None,
        "question": None,
        "created_at": None,
    }
    common_transaction = {
        "row_kind": "transaction",
        "category_name": None,
        "stake_cents": None,
        "payout_cents": None,
        "settled_at": None,
        "revealed_at": None,
        "pnl_cents": None,
        "accuracy_score": None,
        "locked_at": None,
        "transaction_type": "stake",
        "amount_cents": -200,
        "balance_after_cents": 9_800,
    }
    first_prediction_id = uuid.uuid4()
    second_prediction_id = uuid.uuid4()
    rows = [
        row(
            **common_prediction,
            row_id=second_prediction_id,
            locked_at=now,
        ),
        row(
            **common_transaction,
            row_id=uuid.uuid4(),
            transaction_prediction_id=second_prediction_id,
            question="Second question",
            created_at=now,
        ),
        row(
            **common_prediction,
            row_id=first_prediction_id,
            locked_at=now - timedelta(minutes=1),
        ),
        row(
            **common_transaction,
            row_id=uuid.uuid4(),
            transaction_prediction_id=first_prediction_id,
            question="First question",
            created_at=now - timedelta(minutes=1),
        ),
    ]

    predictions, transactions = _split_bootstrap_rows(rows)

    assert [prediction.id for prediction in predictions] == [
        first_prediction_id,
        second_prediction_id,
    ]
    assert [question for _, question, _ in transactions] == [
        "Second question",
        "First question",
    ]
