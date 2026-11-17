"""Scheduling algorithms (Strategy pattern).

Every strategy is a pure function of (state, quality, today): no Flask, no database,
no date.today(). That makes each one easy to test and easy to swap.
"""

from abc import ABC, abstractmethod
from datetime import date, timedelta

from scheduler.models import CardState

# Review buttons and the quality score (0-5) each one sends.
AGAIN, HARD, GOOD, EASY = 0, 3, 4, 5
RATING_QUALITIES = (AGAIN, HARD, GOOD, EASY)  # in button order

PASSING_QUALITY = 3       # below this, the card was forgotten (a lapse)
MIN_EASE = 1.3
LAPSE_EASE_PENALTY = 0.2  # decision D1: a lapse lowers ease, unlike original SM-2
MAX_BOX = 5               # Leitner: the highest box, reviewed every 2^5 = 32 days


class SchedulingStrategy(ABC):
    @abstractmethod
    def next_state(self, state: CardState, quality: int, today: date) -> CardState:
        """Return the card's new state after a review. Never modifies `state`."""


class SM2Strategy(SchedulingStrategy):
    """SuperMemo-2: intervals of 1 day, then 6 days, then growing by the ease factor."""

    def next_state(self, state: CardState, quality: int, today: date) -> CardState:
        _check_quality(quality)
        if quality < PASSING_QUALITY:
            repetitions, interval = 0, 1
            ease = state.ease_factor - LAPSE_EASE_PENALTY
        else:
            repetitions = state.repetitions + 1
            interval = _sm2_interval(state)
            ease = state.ease_factor + _ease_change(quality)
        ease = round(max(MIN_EASE, ease), 2)
        return CardState(ease, interval, repetitions, today + timedelta(days=interval))


class LeitnerStrategy(SchedulingStrategy):
    """Leitner boxes: a success moves the card up one box, a lapse sends it back to box 0.

    The interval is 2^box days. `repetitions` stores the box number; ease is not used.
    """

    def next_state(self, state: CardState, quality: int, today: date) -> CardState:
        _check_quality(quality)
        box = 0 if quality < PASSING_QUALITY else min(state.repetitions + 1, MAX_BOX)
        interval = 2 ** box
        return CardState(state.ease_factor, interval, box, today + timedelta(days=interval))


# Registry: SCHEDULER setting -> strategy class. Adding an algorithm means adding one entry.
STRATEGIES: dict[str, type[SchedulingStrategy]] = {
    "sm2": SM2Strategy,
    "leitner": LeitnerStrategy,
}


def get_strategy(name: str) -> SchedulingStrategy:
    """Build the strategy registered under `name`. Raises ValueError for an unknown name."""
    strategy_class = STRATEGIES.get(name.lower())
    if strategy_class is None:
        raise ValueError(f"Unknown SCHEDULER '{name}'. Choose one of: {', '.join(STRATEGIES)}.")
    return strategy_class()


def _sm2_interval(state: CardState) -> int:
    """Next interval for a successful review, using the ease factor from before this review."""
    if state.repetitions == 0:
        return 1
    if state.repetitions == 1:
        return 6
    return round(state.interval_days * state.ease_factor)


def _ease_change(quality: int) -> float:
    """SM-2 ease update: Easy +0.10, Good 0, Hard -0.14."""
    miss = 5 - quality
    return 0.1 - miss * (0.08 + miss * 0.02)


def _check_quality(quality: int) -> None:
    if not 0 <= quality <= 5:
        raise ValueError(f"Quality must be between 0 and 5, got {quality}.")
