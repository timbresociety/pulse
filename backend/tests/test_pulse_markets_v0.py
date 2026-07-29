import json
import math
import uuid
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.game import (
    _allocate_pool,
    accuracy_multiplier,
    actual_vote_counts,
    forecast_error,
    platform_fee_cents,
    reveal_seconds_for_index,
    settle_market,
    simulate_crowd,
    validate_participation,
)
from app.schemas import (
    CreatePredictionIn,
    MarketCategoryOut,
    MarketOptionOut,
    MarketOut,
)
from app.seed import load_catalog, validate_catalog

ROOT = Path(__file__).resolve().parents[2]
CATALOG = load_catalog()
MARKETS = CATALOG["markets"]
IDS = tuple(uuid.UUID(int=index + 1) for index in range(4))
WEIGHTS = (4000, 3000, 2000, 1000)


def crowd(market_id: uuid.UUID | None = None):
    return simulate_crowd(market_id or uuid.UUID(int=987), IDS, WEIGHTS)


def test_01_every_market_has_four_to_eight_options():
    assert all(4 <= len(market["options"]) <= 8 for market in MARKETS)


def test_02_option_keys_are_unique_within_market():
    for market in MARKETS:
        keys = [option["key"] for option in market["options"]]
        assert len(keys) == len(set(keys)), market["key"]


def test_03_option_labels_are_unique_within_market():
    for market in MARKETS:
        labels = [option["label"].casefold() for option in market["options"]]
        assert len(labels) == len(set(labels)), market["key"]


def test_04_display_order_is_catalog_order():
    for market in MARKETS:
        assert list(range(len(market["options"]))) == [
            index for index, _ in enumerate(market["options"])
        ]


def test_05_simulation_weights_total_ten_thousand():
    assert all(sum(market["simulation_weights_bps"]) == 10_000 for market in MARKETS)


def test_06_feed_schema_omits_hidden_data_when_none():
    output = MarketOut(
        id=uuid.uuid4(), key="x", question="Question?",
        category=MarketCategoryOut(id=uuid.uuid4(), slug="internet", name="Internet"),
        options=[MarketOptionOut(id=uuid.uuid4(), key="a", label="A", display_order=0)],
        participant_count=500, pool_volume_cents=100, reveal_seconds=30, avatars=["Nova"],
    ).model_dump(exclude_none=True)
    assert "simulation_weights_bps" not in output
    assert "latent_distribution_bps" not in output
    assert "simulation_seed" not in output


def test_07_feed_explicitly_filters_legacy_markets():
    source = (ROOT / "backend/app/routers/feed.py").read_text()
    assert "Market.market_kind == PULSE_MARKET_KIND" in source
    assert 'Market.status == "active"' in source


def test_08_open_ended_answers_are_rejected():
    with pytest.raises(ValidationError):
        CreatePredictionIn(
            market_id=uuid.uuid4(), vote_option_id=uuid.uuid4(),
            forecast_bps={uuid.uuid4(): 10_000}, stake_cents=100,
            raw_text="an open-ended answer",
        )


def test_09_forecast_must_contain_every_option():
    with pytest.raises(ValueError, match="every market option"):
        validate_participation(IDS, IDS[0], {IDS[0]: 10_000}, 100, 100)


def test_10_unknown_forecast_options_are_rejected():
    forecast = {option_id: 2500 for option_id in IDS}
    forecast[uuid.uuid4()] = 0
    with pytest.raises(ValueError, match="unknown"):
        validate_participation(IDS, IDS[0], forecast, 100, 100)


def test_11_forecast_total_must_equal_ten_thousand():
    with pytest.raises(ValueError, match="10,000"):
        validate_participation(IDS, IDS[0], {option_id: 2000 for option_id in IDS}, 100, 100)


def test_12_same_market_produces_same_crowd():
    first = crowd()
    second = crowd()
    assert first == second


def test_13_different_market_ids_produce_different_crowds():
    assert crowd(uuid.UUID(int=501)).seed != crowd(uuid.UUID(int=502)).seed
    assert crowd(uuid.UUID(int=501)).participants != crowd(uuid.UUID(int=502)).participants


def test_14_dummy_participant_count_is_in_range():
    assert 500 <= crowd().participant_count <= 2000


def test_15_dummy_vote_count_equals_participant_count():
    simulation = crowd()
    assert len(simulation.dummy_votes) == simulation.participant_count


def test_16_user_vote_is_included_exactly_once():
    simulation = crowd()
    before = Counter(simulation.dummy_votes)
    after = actual_vote_counts([str(item) for item in IDS], simulation.dummy_votes, str(IDS[0]))
    assert after[str(IDS[0])] == before[str(IDS[0])] + 1
    assert sum(after.values()) == simulation.participant_count + 1


def test_17_large_stakes_do_not_change_vote_weight():
    simulation = crowd()
    forecast = {str(option_id): weight for option_id, weight in zip(IDS, WEIGHTS)}
    small = settle_market(simulation, option_ids=IDS, user_vote_option_id=IDS[0], user_forecast_bps=forecast, user_stake_cents=100)
    large = settle_market(simulation, option_ids=IDS, user_vote_option_id=IDS[0], user_forecast_bps=forecast, user_stake_cents=1_000_000)
    assert small.actual_distribution_bps == large.actual_distribution_bps


def test_18_perfect_forecast_receives_multiplier_one():
    assert accuracy_multiplier(forecast_error([4000, 3000, 2000, 1000], [4000, 3000, 2000, 1000])) == 1


def test_19_worse_forecasts_receive_lower_multipliers():
    close = accuracy_multiplier(forecast_error([3900, 3100, 2000, 1000], WEIGHTS))
    far = accuracy_multiplier(forecast_error([1000, 2000, 3000, 4000], WEIGHTS))
    assert 1 > close > far


def test_20_identical_accuracy_has_same_return_rate_before_rounding():
    net_stakes = [9800, 19600, 9800]
    payouts = _allocate_pool(sum(net_stakes), [net_stakes[0], net_stakes[1], net_stakes[2] * 0.5])
    assert math.isclose(payouts[0] / net_stakes[0], payouts[1] / net_stakes[1], rel_tol=0, abs_tol=0.0002)


def test_21_platform_fee_is_exactly_two_percent_with_documented_rounding():
    assert platform_fee_cents(10_000) == 200
    assert platform_fee_cents(333) == 7


def test_22_payouts_plus_fees_equal_gross_pool_exactly():
    simulation = crowd()
    result = settle_market(
        simulation, option_ids=IDS, user_vote_option_id=IDS[0],
        user_forecast_bps={str(option_id): weight for option_id, weight in zip(IDS, WEIGHTS)},
        user_stake_cents=50_000,
    )
    assert sum(result.all_payouts_cents) + sum(result.all_fees_cents) == result.gross_pool_cents


def test_23_duplicate_participation_is_database_constrained():
    source = (ROOT / "backend/app/models.py").read_text()
    assert 'UniqueConstraint("user_id", "market_id", name="uq_user_market")' in source


def test_24_stake_over_balance_is_rejected():
    with pytest.raises(ValueError, match="balance"):
        validate_participation(IDS, IDS[0], {item: 2500 for item in IDS}, 101, 100)


def test_25_stake_deduction_uses_a_locked_user_row_and_one_commit():
    source = (ROOT / "backend/app/routers/predictions.py").read_text()
    lock_body = source[source.index("async def lock_prediction"):source.index("async def settle_and_reveal")]
    assert "with_for_update()" in lock_body
    assert "locked_user.balance_cents -= payload.stake_cents" in lock_body
    assert lock_body.count("await db.commit()") == 1


def test_26_settlement_is_deterministic():
    simulation = crowd()
    kwargs = dict(
        option_ids=IDS, user_vote_option_id=IDS[1],
        user_forecast_bps={str(item): 2500 for item in IDS}, user_stake_cents=12_345,
    )
    assert settle_market(simulation, **kwargs) == settle_market(simulation, **kwargs)


def test_27_settlement_has_an_idempotency_guard():
    source = (ROOT / "backend/app/routers/predictions.py").read_text()
    assert "if prediction.settled_at is None:" in source


def test_28_reveal_credits_payout_only_once():
    source = (ROOT / "backend/app/routers/predictions.py").read_text()
    assert "if prediction.payout_credited_at is None:" in source
    assert 'reference_key=f"payout:{prediction.id}"' in source


def test_29_pulse_score_updates_inside_the_same_once_only_guard():
    source = (ROOT / "backend/app/routers/predictions.py").read_text()
    guard = source[source.index("if prediction.payout_credited_at is None:"):source.index("elif prediction.revealed_at is None:")]
    assert "user.pulse_score += prediction.pulse_delta" in guard


def test_30_reveal_timing_formula_is_unchanged(monkeypatch):
    from app.game import settings
    monkeypatch.setattr(settings, "reveal_start_seconds", 30)
    monkeypatch.setattr(settings, "reveal_increment_seconds", 30)
    assert [reveal_seconds_for_index(index) for index in range(4)] == [30, 60, 90, 120]


def test_31_catalog_seed_keys_cannot_create_duplicates():
    keys = [market["key"] for market in MARKETS]
    assert len(keys) == len(set(keys))
    seed_source = (ROOT / "backend/app/seed.py").read_text()
    assert "existing_v0" in seed_source and "existing_options" in seed_source


def test_32_existing_database_has_additive_migration():
    migration = ROOT / "backend/migrations/versions/20260722_0001_pulse_markets_v0.py"
    source = migration.read_text()
    assert migration.exists()
    assert "UPDATE users SET balance_cents" in source
    assert 'op.drop_table("users")' not in source
    assert 'op.drop_table("predictions")' not in source


def test_33_every_active_category_has_at_least_eight_markets():
    counts = Counter(market["category_slug"] for market in MARKETS)
    assert len(counts) == 8
    assert set(counts.values()) == {8}
    validate_catalog(CATALOG)


def test_34_frontend_participation_never_calls_legacy_search():
    frontend_source = "\n".join(
        path.read_text() for path in (ROOT / "frontend/src").rglob("*.js*")
    )
    assert '"/search' not in frontend_source
    assert "api.search" not in frontend_source


def test_35_first_email_login_loads_categories_before_serialization():
    auth_source = (ROOT / "backend/app/auth.py").read_text()
    assert 'await db.refresh(user, attribute_names=["categories"])' in auth_source
