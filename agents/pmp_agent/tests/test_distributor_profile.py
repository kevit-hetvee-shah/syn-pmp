"""Tests for distributor_profile.py — pure deterministic scoring/classification
logic, no SDK/agent/API involved.
"""

from distributor_profile import (
    PARTNERSHIP_QUESTIONS,
    PRESSURE_QUESTIONS,
    classify,
    compute_dynamic_profile,
    resolve_draft_profile,
    validate_scores,
)


def _max_scores(questions) -> dict[str, int]:
    return {q.key: q.possible_scores[-1] for q in questions}


def _min_scores(questions) -> dict[str, int]:
    return {q.key: q.possible_scores[0] for q in questions}


def test_all_max_scores_sum_to_60_per_dimension() -> None:
    assert sum(_max_scores(PRESSURE_QUESTIONS).values()) == 60
    assert sum(_max_scores(PARTNERSHIP_QUESTIONS).values()) == 60


def test_classify_hedgehog_high_pressure_low_partnership() -> None:
    assert classify(40, 10) == "Hedgehog"


def test_classify_wolf_high_pressure_high_partnership() -> None:
    assert classify(40, 40) == "Wolf"


def test_classify_polar_bear_low_pressure_low_partnership() -> None:
    assert classify(10, 10) == "Polar Bear"


def test_classify_dolphin_low_pressure_high_partnership() -> None:
    assert classify(10, 40) == "Dolphin"


def test_classify_exact_boundary_is_undetermined() -> None:
    assert classify(30, 10) is None
    assert classify(10, 30) is None
    assert classify(30, 30) is None


def test_classify_missing_dimension_is_undetermined() -> None:
    assert classify(None, 40) is None
    assert classify(40, None) is None


def test_compute_dynamic_profile_with_all_max_scores_is_wolf() -> None:
    result = compute_dynamic_profile(_max_scores(PRESSURE_QUESTIONS), _max_scores(PARTNERSHIP_QUESTIONS))
    assert result.pressure_total == 60
    assert result.partnership_total == 60
    assert result.profile == "Wolf"


def test_compute_dynamic_profile_with_all_min_scores_is_polar_bear() -> None:
    result = compute_dynamic_profile(_min_scores(PRESSURE_QUESTIONS), _min_scores(PARTNERSHIP_QUESTIONS))
    assert result.pressure_total == 0
    assert result.partnership_total == 0
    assert result.profile == "Polar Bear"


def test_compute_dynamic_profile_skipping_everything_cannot_be_determined() -> None:
    result = compute_dynamic_profile({}, {})
    assert result.pressure_total is None
    assert result.partnership_total is None
    assert result.profile is None


def test_compute_dynamic_profile_partial_answers_still_scores_what_was_given() -> None:
    result = compute_dynamic_profile({"portfolio": 6}, {})
    assert result.pressure_total == 6
    assert result.partnership_total is None
    assert result.profile is None  # one dimension missing -> undetermined


def test_validate_scores_accepts_empty_and_valid_subset() -> None:
    assert validate_scores({}, PRESSURE_QUESTIONS) == []
    assert validate_scores({"portfolio": 4}, PRESSURE_QUESTIONS) == []


def test_validate_scores_rejects_unknown_key() -> None:
    errors = validate_scores({"not_a_real_question": 4}, PRESSURE_QUESTIONS)
    assert len(errors) == 1
    assert "not_a_real_question" in errors[0]


def test_validate_scores_rejects_value_not_in_possible_scores() -> None:
    errors = validate_scores({"portfolio": 5}, PRESSURE_QUESTIONS)  # portfolio allows 0/2/4/6
    assert len(errors) == 1
    assert "5" in errors[0]


def test_resolve_draft_profile_not_yet_answered() -> None:
    profile, errors = resolve_draft_profile(None, None, {}, {})
    assert profile is None
    assert errors == []


def test_resolve_draft_profile_known_valid() -> None:
    profile, errors = resolve_draft_profile(True, "Dolphin", {}, {})
    assert profile == "Dolphin"
    assert errors == []


def test_resolve_draft_profile_known_invalid_value_is_an_error() -> None:
    profile, errors = resolve_draft_profile(True, "Unicorn", {}, {})
    assert profile is None
    assert errors


def test_resolve_draft_profile_known_but_not_yet_picked_is_not_an_error() -> None:
    """Regression test: switching the radio to "I know it" fires an autosave
    immediately, before the rep has picked a profile — that in-progress state
    must not be rejected as invalid."""
    profile, errors = resolve_draft_profile(True, None, {}, {})
    assert profile is None
    assert errors == []


def test_resolve_draft_profile_dynamic_ignores_client_claimed_profile() -> None:
    profile, errors = resolve_draft_profile(
        False, "Hedgehog", _max_scores(PRESSURE_QUESTIONS), _max_scores(PARTNERSHIP_QUESTIONS)
    )
    assert errors == []
    assert profile == "Wolf"  # computed from scores, not the client's claimed "Hedgehog"


def test_resolve_draft_profile_dynamic_invalid_score_is_an_error() -> None:
    profile, errors = resolve_draft_profile(False, None, {"portfolio": 99}, {})
    assert profile is None
    assert errors
