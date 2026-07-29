from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.users import _wallet_totals


def prediction(*, stake_cents: int, payout_cents: int | None, settled: bool):
    return SimpleNamespace(
        stake_cents=stake_cents,
        payout_cents=payout_cents,
        settled_at=datetime.now(timezone.utc) if settled else None,
    )


def test_unsettled_stakes_do_not_reduce_net_pnl():
    totals = _wallet_totals(
        [
            prediction(stake_cents=5_000, payout_cents=None, settled=False),
            prediction(stake_cents=200, payout_cents=None, settled=False),
        ]
    )

    assert totals == (5_200, 0, 0)


def test_net_pnl_only_includes_settled_predictions():
    totals = _wallet_totals(
        [
            prediction(stake_cents=5_000, payout_cents=None, settled=False),
            prediction(stake_cents=200, payout_cents=350, settled=True),
            prediction(stake_cents=400, payout_cents=100, settled=True),
        ]
    )

    assert totals == (5_600, 450, -150)
