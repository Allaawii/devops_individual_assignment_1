"""Tests for the scheduling strategies. `today` is fixed, so every result is predictable."""

from datetime import date, timedelta

import pytest

from trainer.scheduler.algorithms import (
    AGAIN, EASY, GOOD, HARD, MAX_BOX, MIN_EASE, STRATEGIES,
    LeitnerStrategy, SchedulingStrategy, SM2Strategy, get_strategy,
)
from trainer.scheduler.models import CardState

TODAY = date(2026, 9, 28)
NEW = CardState()


@pytest.fixture
def sm2() -> SM2Strategy:
    return SM2Strategy()


def _review_n_times(strategy, quality: int, times: int, state: CardState = NEW) -> CardState:
    for _ in range(times):
        state = strategy.next_state(state, quality, TODAY)
    return state


# ----- SM-2: successful reviews -----

def test_first_good_review_gives_one_day(sm2):
    state = sm2.next_state(NEW, GOOD, TODAY)
    assert (state.interval_days, state.repetitions, state.ease_factor) == (1, 1, 2.5)


def test_second_good_review_gives_six_days(sm2):
    assert _review_n_times(sm2, GOOD, 2).interval_days == 6


def test_third_good_review_multiplies_by_ease(sm2):
    assert _review_n_times(sm2, GOOD, 3).interval_days == round(6 * 2.5)


def test_interval_uses_the_ease_from_before_the_review(sm2):
    state = CardState(ease_factor=2.0, interval_days=6, repetitions=2)
    after = sm2.next_state(state, EASY, TODAY)
    assert after.interval_days == 12
    assert after.ease_factor == pytest.approx(2.1)


def test_easy_raises_ease_by_a_tenth(sm2):
    assert sm2.next_state(NEW, EASY, TODAY).ease_factor == pytest.approx(2.6)


def test_hard_lowers_ease_by_0_14(sm2):
    assert sm2.next_state(NEW, HARD, TODAY).ease_factor == pytest.approx(2.36)


def test_hard_on_a_new_card_still_counts_as_a_success(sm2):
    state = sm2.next_state(NEW, HARD, TODAY)
    assert (state.interval_days, state.repetitions) == (1, 1)


def test_repeated_hard_never_drops_ease_below_the_floor(sm2):
    assert _review_n_times(sm2, HARD, 20).ease_factor == MIN_EASE


def test_due_date_is_today_plus_interval(sm2):
    state = _review_n_times(sm2, GOOD, 2)
    assert state.due_date == TODAY + timedelta(days=6)


# ----- SM-2: lapses (decision D1: ease drops by 0.2) -----

def test_lapse_resets_repetitions_and_interval(sm2):
    learned = _review_n_times(sm2, GOOD, 3)
    state = sm2.next_state(learned, AGAIN, TODAY)
    assert (state.interval_days, state.repetitions) == (1, 0)
    assert state.due_date == TODAY + timedelta(days=1)


def test_lapse_lowers_ease_by_0_2(sm2):
    assert sm2.next_state(NEW, AGAIN, TODAY).ease_factor == pytest.approx(2.3)


def test_lapse_never_drops_ease_below_the_floor(sm2):
    state = CardState(ease_factor=1.4)
    assert sm2.next_state(state, AGAIN, TODAY).ease_factor == MIN_EASE


def test_quality_below_3_is_a_lapse(sm2):
    learned = _review_n_times(sm2, GOOD, 3)
    assert sm2.next_state(learned, 2, TODAY).repetitions == 0


# ----- SM-2: input handling -----

@pytest.mark.parametrize("quality", [-1, 6])
def test_quality_outside_0_to_5_is_rejected(sm2, quality):
    with pytest.raises(ValueError):
        sm2.next_state(NEW, quality, TODAY)


def test_input_state_is_not_modified(sm2):
    state = CardState(ease_factor=2.5, interval_days=6, repetitions=2)
    sm2.next_state(state, GOOD, TODAY)
    assert state == CardState(ease_factor=2.5, interval_days=6, repetitions=2)


# ----- Leitner -----

@pytest.fixture
def leitner() -> LeitnerStrategy:
    return LeitnerStrategy()


def test_leitner_success_moves_new_card_to_box_1(leitner):
    state = leitner.next_state(NEW, GOOD, TODAY)
    assert (state.repetitions, state.interval_days) == (1, 2)
    assert state.due_date == TODAY + timedelta(days=2)


def test_leitner_interval_doubles_with_each_box(leitner):
    intervals = [_review_n_times(leitner, GOOD, n).interval_days for n in (1, 2, 3)]
    assert intervals == [2, 4, 8]


def test_leitner_box_is_capped(leitner):
    state = _review_n_times(leitner, EASY, MAX_BOX + 3)
    assert (state.repetitions, state.interval_days) == (MAX_BOX, 2 ** MAX_BOX)


def test_leitner_lapse_sends_card_back_to_box_0(leitner):
    state = leitner.next_state(_review_n_times(leitner, GOOD, 3), AGAIN, TODAY)
    assert (state.repetitions, state.interval_days) == (0, 1)


@pytest.mark.parametrize("quality", [AGAIN, HARD, GOOD, EASY])
def test_leitner_never_changes_ease(leitner, quality):
    assert leitner.next_state(NEW, quality, TODAY).ease_factor == NEW.ease_factor


def test_leitner_rejects_invalid_quality(leitner):
    with pytest.raises(ValueError):
        leitner.next_state(NEW, 6, TODAY)


# ----- registry -----

@pytest.mark.parametrize("name, expected", [("sm2", SM2Strategy), ("leitner", LeitnerStrategy),
                                            ("SM2", SM2Strategy)])
def test_get_strategy_builds_the_registered_class(name, expected):
    assert isinstance(get_strategy(name), expected)


def test_unknown_strategy_fails_with_the_valid_names():
    with pytest.raises(ValueError, match="sm2, leitner"):
        get_strategy("sm3")


def test_every_registered_class_is_a_scheduling_strategy():
    assert all(issubclass(cls, SchedulingStrategy) for cls in STRATEGIES.values())
