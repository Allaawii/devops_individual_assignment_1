"""Scheduler storage: abstract interfaces, plus their SQLite implementations.

Services depend on the abstract classes, so tests can pass in-memory fakes.
Repositories never commit; the request teardown in trainer.db does.
"""

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import date

from trainer.scheduler.models import Card, CardState, Review

GetConnection = Callable[[], sqlite3.Connection]

CARD_COLUMNS = "id, card_type, word_id, sentence_id, ease_factor, interval_days, repetitions, due_date"


class CardRepository(ABC):
    """Stores cards and their scheduling state."""

    @abstractmethod
    def ensure_sentence_card(self, sentence_id: int) -> None:
        """Create a new card for the sentence unless it already has one."""

    @abstractmethod
    def ensure_word_cards(self, word_ids: Iterable[int]) -> None:
        """Create a new card for each word that does not have one yet."""

    @abstractmethod
    def get(self, card_id: int) -> Card | None:
        """Return the card, or None if the id is unknown."""

    @abstractmethod
    def next_due(self, today: date) -> Card | None:
        """The reviewed card that has been due the longest (due_date <= today), or None."""

    @abstractmethod
    def next_new(self) -> Card | None:
        """The never-reviewed card with the lowest id, or None."""

    @abstractmethod
    def save_state(self, card_id: int, state: CardState) -> None:
        """Store the card's new scheduling state."""

    @abstractmethod
    def count_due(self, today: date) -> int:
        """Reviewed cards that are due on or before `today`."""

    @abstractmethod
    def count_new(self) -> int:
        """Cards that have never been reviewed."""

    @abstractmethod
    def count_all(self) -> int:
        """All cards."""


class ReviewLog(ABC):
    """Append-only history of reviews."""

    @abstractmethod
    def add(self, review: Review) -> None:
        """Record one review."""

    @abstractmethod
    def count_reviews_on(self, day: date) -> int:
        """Reviews of any card made on `day`."""

    @abstractmethod
    def count_first_reviews_on(self, day: date) -> int:
        """Cards whose very first review was on `day`, i.e. new cards introduced that day."""


class SqliteCardRepository(CardRepository):
    def __init__(self, get_conn: GetConnection) -> None:
        self._get_conn = get_conn

    def ensure_sentence_card(self, sentence_id: int) -> None:
        # OR IGNORE: the partial unique index ux_cards_sentence makes a second insert a no-op.
        self._get_conn().execute(
            "INSERT OR IGNORE INTO cards (card_type, sentence_id) VALUES ('sentence', ?)",
            (sentence_id,),
        )

    def ensure_word_cards(self, word_ids: Iterable[int]) -> None:
        self._get_conn().executemany(
            "INSERT OR IGNORE INTO cards (card_type, word_id) VALUES ('word', ?)",
            [(word_id,) for word_id in word_ids],
        )

    def get(self, card_id: int) -> Card | None:
        return self._one(f"SELECT {CARD_COLUMNS} FROM cards WHERE id = ?", (card_id,))

    def next_due(self, today: date) -> Card | None:
        return self._one(
            f"SELECT {CARD_COLUMNS} FROM cards WHERE due_date <= ? ORDER BY due_date, id LIMIT 1",
            (today.isoformat(),),
        )

    def next_new(self) -> Card | None:
        return self._one(
            f"SELECT {CARD_COLUMNS} FROM cards WHERE due_date IS NULL ORDER BY id LIMIT 1", ()
        )

    def save_state(self, card_id: int, state: CardState) -> None:
        self._get_conn().execute(
            "UPDATE cards SET ease_factor = ?, interval_days = ?, repetitions = ?, due_date = ? "
            "WHERE id = ?",
            (state.ease_factor, state.interval_days, state.repetitions,
             state.due_date.isoformat() if state.due_date else None, card_id),
        )

    def count_due(self, today: date) -> int:
        return self._count("SELECT COUNT(*) FROM cards WHERE due_date <= ?", (today.isoformat(),))

    def count_new(self) -> int:
        return self._count("SELECT COUNT(*) FROM cards WHERE due_date IS NULL", ())

    def count_all(self) -> int:
        return self._count("SELECT COUNT(*) FROM cards", ())

    def _one(self, sql: str, params: tuple) -> Card | None:
        row = self._get_conn().execute(sql, params).fetchone()
        return _to_card(row) if row else None

    def _count(self, sql: str, params: tuple) -> int:
        return self._get_conn().execute(sql, params).fetchone()[0]


class SqliteReviewLog(ReviewLog):
    def __init__(self, get_conn: GetConnection) -> None:
        self._get_conn = get_conn

    def add(self, review: Review) -> None:
        self._get_conn().execute(
            "INSERT INTO reviews (card_id, reviewed_at, quality, resulting_interval, resulting_ease) "
            "VALUES (?, ?, ?, ?, ?)",
            (review.card_id, review.reviewed_at.isoformat(timespec="seconds"), review.quality,
             review.resulting_interval, review.resulting_ease),
        )

    def count_reviews_on(self, day: date) -> int:
        return self._get_conn().execute(
            "SELECT COUNT(*) FROM reviews WHERE date(reviewed_at) = ?", (day.isoformat(),)
        ).fetchone()[0]

    def count_first_reviews_on(self, day: date) -> int:
        return self._get_conn().execute(
            "SELECT COUNT(*) FROM "
            "(SELECT card_id, MIN(reviewed_at) AS first FROM reviews GROUP BY card_id) "
            "WHERE date(first) = ?",
            (day.isoformat(),),
        ).fetchone()[0]


def _to_card(row: sqlite3.Row) -> Card:
    due = row["due_date"]
    state = CardState(row["ease_factor"], row["interval_days"], row["repetitions"],
                      date.fromisoformat(due) if due else None)
    return Card(row["id"], row["card_type"], row["word_id"], row["sentence_id"], state)
