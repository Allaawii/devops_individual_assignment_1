"""Records for the scheduler domain."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CardState:
    """Everything a scheduling algorithm needs to know about a card. The defaults describe a new card."""

    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    due_date: date | None = None  # None = new, never reviewed
