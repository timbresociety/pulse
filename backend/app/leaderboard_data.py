"""Deterministic dummy leaderboard population and compact ranking windows."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from functools import lru_cache

DUMMY_COMPETITOR_COUNT = 5_200
VISIBLE_TOP_COUNT = 10
VISIBLE_NEIGHBOR_COUNT = 3

_ADJECTIVES = (
    "Atomic",
    "Blue",
    "Bold",
    "Bright",
    "Calm",
    "Cosmic",
    "Electric",
    "Feral",
    "Golden",
    "Hyper",
    "Indie",
    "Lucky",
    "Lunar",
    "Mint",
    "Neon",
    "Nova",
    "Pixel",
    "Quiet",
    "Rapid",
    "Rare",
    "Retro",
    "Silver",
    "Solar",
    "Sonic",
    "Swift",
    "Velvet",
    "Viral",
    "Wild",
)

_NOUNS = (
    "Aura",
    "Beacon",
    "Call",
    "Crowd",
    "Echo",
    "Forecast",
    "Hunch",
    "Lens",
    "Mood",
    "Oracle",
    "Pulse",
    "Radar",
    "Reader",
    "Scout",
    "Signal",
    "Spark",
    "Trend",
    "Vibe",
    "Wave",
)


@dataclass(frozen=True)
class LeaderboardProfile:
    display_name: str
    avatar_url: str | None
    pulse_score: int
    average_accuracy: float
    win_rate: float
    markets_played: int
    current_streak: int
    is_you: bool = False


@lru_cache(maxsize=8)
def generated_competitors(
    count: int = DUMMY_COMPETITOR_COUNT,
    minimum_pulse_score: int = 1_001,
) -> tuple[LeaderboardProfile, ...]:
    """Build a stable, believable score ladder without thousands of DB rows."""
    if count < 1:
        return ()

    rng = random.Random(0x50554C5345)
    score_span = 350
    profiles: list[LeaderboardProfile] = []
    denominator = max(count - 1, 1)

    for index in range(count):
        # A gentle curve packs more players near the entry score. A strong
        # market result therefore moves a new player by hundreds of places,
        # while the upper ranks remain increasingly competitive.
        ladder_position = 1 - (index / denominator)
        pulse_score = minimum_pulse_score + round(
            score_span * (ladder_position**1.35)
        )
        skill = (pulse_score - minimum_pulse_score) / score_span
        accuracy = min(79.0, max(49.0, 52.0 + skill * 23 + rng.uniform(-2.2, 2.2)))
        win_rate = min(0.66, max(0.38, 0.43 + skill * 0.18 + rng.uniform(-0.025, 0.025)))
        markets_played = rng.randint(18, 260)
        current_streak = min(12, int(rng.expovariate(0.55)))
        adjective = _ADJECTIVES[rng.randrange(len(_ADJECTIVES))]
        noun = _NOUNS[rng.randrange(len(_NOUNS))]

        profiles.append(
            LeaderboardProfile(
                display_name=f"{adjective}{noun}{index + 1:04d}",
                avatar_url=None,
                pulse_score=pulse_score,
                average_accuracy=round(accuracy, 1),
                win_rate=round(win_rate, 3),
                markets_played=markets_played,
                current_streak=current_streak,
            )
        )

    return tuple(profiles)


def complete_dummy_field(
    persisted_profiles: list[LeaderboardProfile],
    *,
    starting_pulse_score: int,
    target_count: int = DUMMY_COMPETITOR_COUNT,
) -> list[LeaderboardProfile]:
    """Keep curated profiles and fill the remaining field deterministically."""
    minimum_dummy_score = starting_pulse_score + 1
    profiles = [
        replace(profile, pulse_score=max(profile.pulse_score, minimum_dummy_score))
        for profile in persisted_profiles
    ]
    if len(profiles) >= target_count:
        return profiles

    reserved_names = {profile.display_name.casefold() for profile in profiles}
    generated = generated_competitors(target_count, minimum_dummy_score)
    for profile in generated:
        if profile.display_name.casefold() in reserved_names:
            continue
        profiles.append(profile)
        if len(profiles) == target_count:
            break
    return profiles


def ranked_window(
    dummy_profiles: list[LeaderboardProfile],
    user_profile: LeaderboardProfile,
    *,
    top_count: int = VISIBLE_TOP_COUNT,
    neighbor_count: int = VISIBLE_NEIGHBOR_COUNT,
) -> tuple[int, int, list[dict]]:
    """Rank the full field but return only the leaders and the user's neighborhood."""
    candidates = [*dummy_profiles, replace(user_profile, is_you=True)]
    candidates.sort(
        key=lambda profile: (
            -profile.pulse_score,
            0 if profile.is_you else 1,
            profile.display_name.casefold(),
        )
    )

    user_index = next(
        index for index, profile in enumerate(candidates) if profile.is_you
    )
    visible_indexes = set(range(min(top_count, len(candidates))))
    visible_indexes.update(
        range(
            max(0, user_index - neighbor_count),
            min(len(candidates), user_index + neighbor_count + 1),
        )
    )

    rows = [
        {
            "rank": index + 1,
            "display_name": candidates[index].display_name,
            "avatar_url": candidates[index].avatar_url,
            "pulse_score": candidates[index].pulse_score,
            "average_accuracy": candidates[index].average_accuracy,
            "win_rate": candidates[index].win_rate,
            "markets_played": candidates[index].markets_played,
            "current_streak": candidates[index].current_streak,
            "is_you": candidates[index].is_you,
        }
        for index in sorted(visible_indexes)
    ]
    return len(candidates), user_index + 1, rows
