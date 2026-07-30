"""Deterministic Pulse Markets v0 crowd simulation and settlement.

The market id and authored population weights are the complete source of
simulation state. No dummy participant rows are persisted and no unseeded
randomness is used.
"""

from __future__ import annotations

import hashlib
import math
import random
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Prediction

PULSE_MARKET_KIND = "pulse_poll_v0"
PLATFORM_FEE_BPS = 200


@dataclass(frozen=True)
class DummyParticipant:
    vote_option_id: str
    forecast_bps: dict[str, int]
    stake_cents: int


@dataclass(frozen=True)
class CrowdSimulation:
    seed: str
    participant_count: int
    latent_distribution_bps: dict[str, int]
    participants: tuple[DummyParticipant, ...]

    @property
    def dummy_votes(self) -> tuple[str, ...]:
        return tuple(participant.vote_option_id for participant in self.participants)

    @property
    def pool_volume_cents(self) -> int:
        return sum(participant.stake_cents for participant in self.participants)

    @property
    def net_pool_volume_cents(self) -> int:
        return sum(
            participant.stake_cents - platform_fee_cents(participant.stake_cents)
            for participant in self.participants
        )


@dataclass(frozen=True)
class SettlementResult:
    actual_distribution_bps: dict[str, int]
    forecast_error: float
    accuracy_multiplier: float
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
    gross_pool_cents: int
    net_pool_cents: int
    user_fee_cents: int
    payout_cents: int
    pnl_cents: int
    pulse_delta: int
    all_stakes_cents: tuple[int, ...]
    all_fees_cents: tuple[int, ...]
    all_payouts_cents: tuple[int, ...]


def reveal_seconds_for_index(index: int) -> int:
    """Return the preserved linear, per-user reveal delay for a 0-based lock index."""
    return settings.reveal_start_seconds + index * settings.reveal_increment_seconds


async def user_locked_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(Prediction).where(Prediction.user_id == user_id)
    )
    return result.scalar_one()


def simulation_seed(market_id: uuid.UUID | str) -> str:
    return hashlib.sha256(f"pulse-v0|{market_id}".encode()).hexdigest()


def _rng(market_id: uuid.UUID | str) -> random.Random:
    return random.Random(int(simulation_seed(market_id), 16))


def normalize_bps(values: Iterable[float], total: int = 10_000) -> list[int]:
    """Normalize non-negative weights with deterministic largest-remainder rounding."""
    clean = [max(0.0, float(value)) for value in values]
    if not clean:
        raise ValueError("At least one weight is required")
    weight_sum = sum(clean)
    if weight_sum <= 0:
        clean = [1.0] * len(clean)
        weight_sum = float(len(clean))
    raw = [value * total / weight_sum for value in clean]
    floors = [math.floor(value) for value in raw]
    remaining = total - sum(floors)
    order = sorted(range(len(raw)), key=lambda index: (-(raw[index] - floors[index]), index))
    for index in order[:remaining]:
        floors[index] += 1
    return floors


def platform_fee_cents(stake_cents: int) -> int:
    """Round a positive 2% fee to the nearest cent, with half cents rounded up."""
    return (stake_cents * PLATFORM_FEE_BPS + 5_000) // 10_000


def validate_participation(
    option_ids: Sequence[uuid.UUID | str],
    vote_option_id: uuid.UUID | str,
    forecast_bps: dict[uuid.UUID | str, int],
    stake_cents: int,
    balance_cents: int,
) -> None:
    """Shared domain validation used by the API and unit tests."""
    expected = {str(option_id) for option_id in option_ids}
    vote_id = str(vote_option_id)
    forecast = {str(option_id): value for option_id, value in forecast_bps.items()}
    if vote_id not in expected:
        raise ValueError("Selected vote option does not belong to this market")
    if expected - set(forecast):
        raise ValueError("Forecast must contain every market option")
    if set(forecast) - expected:
        raise ValueError("Forecast contains unknown market options")
    if any(not isinstance(value, int) or value < 0 or value > 10_000 for value in forecast.values()):
        raise ValueError("Forecast allocations must be integer basis points from 0 to 10,000")
    if sum(forecast.values()) != 10_000:
        raise ValueError("Forecast must total exactly 10,000 basis points")
    if stake_cents <= 0:
        raise ValueError("Stake must be positive")
    if stake_cents > balance_cents:
        raise ValueError("Insufficient test-credit balance")


def forecast_error(forecast_bps: Sequence[int], actual_bps: Sequence[int]) -> float:
    if len(forecast_bps) != len(actual_bps):
        raise ValueError("Forecast and actual distributions must have the same size")
    return sum(((forecast - actual) / 10_000) ** 2 for forecast, actual in zip(forecast_bps, actual_bps))


def accuracy_multiplier(error: float) -> float:
    return math.exp(-10 * error)


def _weighted_choice(rng: random.Random, weights: Sequence[int]) -> int:
    pick = rng.randrange(sum(weights))
    cursor = 0
    for index, weight in enumerate(weights):
        cursor += weight
        if pick < cursor:
            return index
    return len(weights) - 1


def _dummy_forecast(
    rng: random.Random,
    latent: Sequence[int],
    own_vote_index: int,
) -> list[int]:
    roll = rng.random()
    if roll < 0.12:
        skill = rng.uniform(0.88, 0.99)
    elif roll < 0.72:
        skill = rng.uniform(0.46, 0.87)
    else:
        skill = rng.uniform(0.05, 0.45)

    # A Dirichlet-like personal prior produces both reasonable and poor reads.
    concentration = rng.uniform(0.55, 2.4)
    prior = [rng.gammavariate(concentration, 1.0) for _ in latent]
    prior_bps = normalize_bps(prior)
    values = [skill * base + (1 - skill) * personal for base, personal in zip(latent, prior_bps)]

    noise_scale = 45 + (1 - skill) * 330
    values = [max(0.0, value + rng.gauss(0, noise_scale)) for value in values]
    own_vote_bias = rng.uniform(90, 420)
    if roll > 0.94:
        own_vote_bias += rng.uniform(700, 1600)
    values[own_vote_index] += own_vote_bias
    return normalize_bps(values)


def _dummy_stake_cents(rng: random.Random) -> int:
    # Median is roughly $45; most stakes remain under $100, with a thin whale tail.
    if rng.random() < 0.018:
        return rng.randint(100_000, 1_000_000)
    if rng.random() < 0.075:
        return rng.randint(10_000, 100_000)
    return max(100, min(99_999, int(round(rng.lognormvariate(math.log(4_500), 0.82)))))


@lru_cache(maxsize=512)
def _simulate_crowd_cached(
    market_id: str,
    option_ids: tuple[str, ...],
    authored_weights_bps: tuple[int, ...],
) -> CrowdSimulation:
    if len(option_ids) != len(authored_weights_bps):
        raise ValueError("Every option requires an authored simulation weight")
    if not 4 <= len(option_ids) <= 8:
        raise ValueError("Pulse polls require four to eight options")
    if any(not isinstance(weight, int) for weight in authored_weights_bps):
        raise ValueError("Simulation weights must be integers")
    if sum(authored_weights_bps) != 10_000:
        raise ValueError("Simulation weights must total 10,000 basis points")

    rng = _rng(market_id)
    participant_count = rng.randint(500, 2_000)
    perturbation = [
        max(1.0, weight * (1 + rng.uniform(-0.11, 0.11)))
        for weight in authored_weights_bps
    ]
    latent = normalize_bps(perturbation)

    participants: list[DummyParticipant] = []
    for _ in range(participant_count):
        vote_index = _weighted_choice(rng, latent)
        forecast = _dummy_forecast(rng, latent, vote_index)
        participants.append(
            DummyParticipant(
                vote_option_id=option_ids[vote_index],
                forecast_bps=dict(zip(option_ids, forecast)),
                stake_cents=_dummy_stake_cents(rng),
            )
        )

    return CrowdSimulation(
        seed=simulation_seed(market_id),
        participant_count=participant_count,
        latent_distribution_bps=dict(zip(option_ids, latent)),
        participants=tuple(participants),
    )


def simulate_crowd(
    market_id: uuid.UUID | str,
    option_ids: Sequence[uuid.UUID | str],
    authored_weights_bps: Sequence[int],
) -> CrowdSimulation:
    return _simulate_crowd_cached(
        str(market_id),
        tuple(str(option_id) for option_id in option_ids),
        tuple(authored_weights_bps),
    )


def actual_vote_counts(
    option_ids: Sequence[str], dummy_votes: Sequence[str], user_vote_option_id: str
) -> dict[str, int]:
    counts = {option_id: 0 for option_id in option_ids}
    for option_id in dummy_votes:
        counts[option_id] += 1
    # A user's vote is a single vote irrespective of stake.
    counts[user_vote_option_id] += 1
    return counts


def _actual_distribution(
    option_ids: Sequence[str], dummy_votes: Sequence[str], user_vote_option_id: str
) -> dict[str, int]:
    counts = actual_vote_counts(option_ids, dummy_votes, user_vote_option_id)
    normalized = normalize_bps(counts[option_id] for option_id in option_ids)
    return dict(zip(option_ids, normalized))


def _allocate_pool(net_pool_cents: int, weighted_stakes: Sequence[float]) -> list[int]:
    total_weight = sum(weighted_stakes)
    if total_weight <= 0:
        raise ValueError("Weighted stake pool must be positive")
    raw = [net_pool_cents * weight / total_weight for weight in weighted_stakes]
    floors = [math.floor(value) for value in raw]
    remaining = net_pool_cents - sum(floors)
    order = sorted(range(len(raw)), key=lambda index: (-(raw[index] - floors[index]), index))
    for index in order[:remaining]:
        floors[index] += 1
    return floors


def _quantile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("Quantiles require at least one value")
    if not 0 <= quantile <= 1:
        raise ValueError("Quantile must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def settle_market(
    crowd: CrowdSimulation,
    *,
    option_ids: Sequence[uuid.UUID | str],
    user_vote_option_id: uuid.UUID | str,
    user_forecast_bps: dict[str, int] | dict[uuid.UUID, int],
    user_stake_cents: int,
) -> SettlementResult:
    ids = [str(option_id) for option_id in option_ids]
    vote_id = str(user_vote_option_id)
    forecast = {str(key): value for key, value in user_forecast_bps.items()}
    if set(forecast) != set(ids) or sum(forecast.values()) != 10_000:
        raise ValueError("User forecast must contain every option and total 10,000")
    if vote_id not in ids:
        raise ValueError("User vote option does not belong to the market")
    if user_stake_cents <= 0:
        raise ValueError("Stake must be positive")

    actual = _actual_distribution(ids, crowd.dummy_votes, vote_id)
    actual_values = [actual[option_id] for option_id in ids]

    dummy_errors = [
        forecast_error([participant.forecast_bps[option_id] for option_id in ids], actual_values)
        for participant in crowd.participants
    ]
    user_error = forecast_error([forecast[option_id] for option_id in ids], actual_values)
    errors = dummy_errors + [user_error]
    multipliers = [accuracy_multiplier(error) for error in errors]
    stakes = [participant.stake_cents for participant in crowd.participants] + [user_stake_cents]
    fees = [platform_fee_cents(stake) for stake in stakes]
    net_stakes = [stake - fee for stake, fee in zip(stakes, fees)]
    weighted_stakes = [net * multiplier for net, multiplier in zip(net_stakes, multipliers)]
    gross_pool = sum(stakes)
    net_pool = sum(net_stakes)
    payouts = _allocate_pool(net_pool, weighted_stakes)

    better_count = sum(error < user_error for error in dummy_errors)
    at_or_worse_count = sum(error >= user_error for error in dummy_errors)
    percentile = at_or_worse_count / len(dummy_errors)
    user_multiplier = multipliers[-1]
    user_payout = payouts[-1]
    dummy_accuracy_scores = [multiplier * 100 for multiplier in multipliers[:-1]]
    user_weighted_stake = weighted_stakes[-1]
    total_weighted_stake = sum(weighted_stakes)
    other_weighted_stake = total_weighted_stake - user_weighted_stake
    break_even_denominator = net_stakes[-1] * (net_pool - user_stake_cents)
    break_even_accuracy_score = (
        (user_stake_cents * other_weighted_stake / break_even_denominator) * 100
        if break_even_denominator > 0
        else 101.0
    )

    return SettlementResult(
        actual_distribution_bps=actual,
        forecast_error=user_error,
        accuracy_multiplier=user_multiplier,
        accuracy_score=user_multiplier * 100,
        accuracy_percentile=percentile,
        forecast_rank=better_count + 1,
        total_participants=len(crowd.participants) + 1,
        crowd_median_accuracy_score=_quantile(dummy_accuracy_scores, 0.5),
        crowd_top_quartile_accuracy_score=_quantile(dummy_accuracy_scores, 0.75),
        crowd_top_ten_accuracy_score=_quantile(dummy_accuracy_scores, 0.9),
        break_even_accuracy_score=break_even_accuracy_score,
        accuracy_weighted_stake_cents=user_weighted_stake,
        weighted_pool_share=user_weighted_stake / total_weighted_stake,
        gross_pool_cents=gross_pool,
        net_pool_cents=net_pool,
        user_fee_cents=fees[-1],
        payout_cents=user_payout,
        pnl_cents=user_payout - user_stake_cents,
        pulse_delta=round((percentile - 0.5) * 40),
        all_stakes_cents=tuple(stakes),
        all_fees_cents=tuple(fees),
        all_payouts_cents=tuple(payouts),
    )


DUMMY_AVATARS = (
    "Nova", "Mika", "Jules", "Rin", "Ari", "Sol", "Zoya", "Theo"
)


def market_avatar_names(market_id: uuid.UUID | str) -> list[str]:
    rng = _rng(f"avatars|{market_id}")
    count = rng.randint(3, 5)
    return rng.sample(list(DUMMY_AVATARS), count)
