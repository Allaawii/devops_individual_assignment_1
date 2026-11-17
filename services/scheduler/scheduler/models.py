"""Records for the scheduler domain."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, NamedTuple

WORD_CARD = "word"
SENTENCE_CARD = "sentence"


@dataclass(frozen=True)
class CardState:
    """Everything a scheduling algorithm needs to know about a card. The defaults describe a new card."""

    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    due_date: date | None = None  # None = new, never reviewed


@dataclass(frozen=True)
class Card:
    """A flashcard. It points at content by ID only (ADR-3): the ids live in the content service's
    database. Exactly one of the two ids is set."""

    id: int
    card_type: str  # WORD_CARD or SENTENCE_CARD
    word_id: int | None
    sentence_id: int | None
    state: CardState


@dataclass(frozen=True)
class Review:
    """One rating of one card, kept as history."""

    card_id: int
    reviewed_at: datetime
    quality: int
    resulting_interval: int
    resulting_ease: float


@dataclass(frozen=True)
class ReviewStats:
    """The numbers shown on the dashboard."""

    due_now: int
    new_left_today: int
    reviewed_today: int
    total_cards: int


class NewCard(NamedTuple):
    """A card to create: (card_type, word_id, sentence_id), with exactly one of the ids set."""

    card_type: str
    word_id: int | None
    sentence_id: int | None


@dataclass(frozen=True)
class NextReview:
    """Everything the review screen needs: the card, its text from content, and the numbers."""

    card: Card
    content: dict[str, Any]          # content's GET /sentences/{id} or GET /words/{id} body
    intervals: dict[int, int]        # quality -> days until the card comes back
    stats: ReviewStats


@dataclass(frozen=True)
class PlacementOutcome:
    level: int
    level_name: str
    skipped: int                     # cards marked as already known
