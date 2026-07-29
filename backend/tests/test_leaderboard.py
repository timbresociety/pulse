from app.leaderboard_data import (
    DUMMY_COMPETITOR_COUNT,
    LeaderboardProfile,
    complete_dummy_field,
    generated_competitors,
    ranked_window,
)

STARTING_PULSE_SCORE = 1_000


def user_profile(pulse_score: int) -> LeaderboardProfile:
    return LeaderboardProfile(
        display_name="New Player",
        avatar_url=None,
        pulse_score=pulse_score,
        average_accuracy=0,
        win_rate=0,
        markets_played=0,
        current_streak=0,
        is_you=True,
    )


def test_dummy_population_is_stable_and_above_five_thousand():
    first = generated_competitors()
    second = generated_competitors()

    assert first is second
    assert len(first) == DUMMY_COMPETITOR_COUNT
    assert DUMMY_COMPETITOR_COUNT > 5_000


def test_new_user_starts_at_the_bottom_of_the_full_field():
    competitors = complete_dummy_field(
        [],
        starting_pulse_score=STARTING_PULSE_SCORE,
    )
    total_players, user_rank, rows = ranked_window(
        competitors,
        user_profile(STARTING_PULSE_SCORE),
    )

    assert min(profile.pulse_score for profile in competitors) > STARTING_PULSE_SCORE
    assert total_players == DUMMY_COMPETITOR_COUNT + 1
    assert user_rank == total_players
    assert rows[-1]["is_you"] is True
    assert rows[-1]["rank"] == total_players


def test_user_climbs_and_has_players_below_after_a_score_gain():
    competitors = complete_dummy_field(
        [],
        starting_pulse_score=STARTING_PULSE_SCORE,
    )
    total_players, user_rank, rows = ranked_window(
        competitors,
        user_profile(STARTING_PULSE_SCORE + 20),
    )
    user_row_index = next(index for index, row in enumerate(rows) if row["is_you"])

    assert user_rank < total_players
    assert rows[user_row_index + 1]["rank"] == user_rank + 1
    assert rows[user_row_index - 1]["rank"] == user_rank - 1


def test_user_reaches_the_top_when_performance_exceeds_the_field():
    competitors = complete_dummy_field(
        [],
        starting_pulse_score=STARTING_PULSE_SCORE,
    )
    _, user_rank, rows = ranked_window(competitors, user_profile(2_000))

    assert user_rank == 1
    assert rows[0]["is_you"] is True
