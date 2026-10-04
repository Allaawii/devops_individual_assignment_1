"""Scheduler storage: abstract interfaces, plus their SQLite implementations.

Services depend on the abstract classes, so tests can pass in-memory fakes.
Repositories never commit; the request teardown in trainer.db does.
"""

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import date

from trainer.db import SqliteRepository
from trainer.scheduler.models import SENTENCE_CARD, WORD_CARD, Card, CardState, Review

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
    def new_cards_for(self, sentence_ids: list[int], word_ids: list[int]) -> list[Card]:
        """The never-reviewed cards of these sentences and words, in id order."""

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


class SettingsStore(ABC):
    """Learner preferences stored as key/value text."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """The stored value, or None if it was never set."""

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """Store a value, replacing any earlier one."""


class SqliteCardRepository(SqliteRepository, CardRepository):
    # OR IGNORE: the partial unique indexes (ux_cards_sentence, ux_cards_word) make a repeat insert a no-op.
    def ensure_sentence_card(self, sentence_id: int) -> None:
        self._execute("INSERT OR IGNORE INTO cards (card_type, sentence_id) VALUES (?, ?)",
                      (SENTENCE_CARD, sentence_id))

    def ensure_word_cards(self, word_ids: Iterable[int]) -> None:
        self._execute_many("INSERT OR IGNORE INTO cards (card_type, word_id) VALUES (?, ?)",
                           [(WORD_CARD, word_id) for word_id in word_ids])

    def get(self, card_id: int) -> Card | None:
        return self._card(f"SELECT {CARD_COLUMNS} FROM cards WHERE id = ?", (card_id,))

    def next_due(self, today: date) -> Card | None:
        return self._card(f"SELECT {CARD_COLUMNS} FROM cards WHERE due_date <= ? ORDER BY due_date, id LIMIT 1",
                          (today.isoformat(),))

    def next_new(self) -> Card | None:
        return self._card(f"SELECT {CARD_COLUMNS} FROM cards WHERE due_date IS NULL ORDER BY id LIMIT 1")

    def new_cards_for(self, sentence_ids: list[int], word_ids: list[int]) -> list[Card]:
        rows = []
        for column, ids in (("sentence_id", sentence_ids), ("word_id", word_ids)):
            # {{ids}} survives the f-string as {ids}, which _fetch_all_in fills with placeholders.
            rows += self._fetch_all_in(
                f"SELECT {CARD_COLUMNS} FROM cards WHERE due_date IS NULL AND {column} IN ({{ids}})", ids)
        return sorted((_to_card(row) for row in rows), key=lambda card: card.id)

    def save_state(self, card_id: int, state: CardState) -> None:
        self._execute(
            "UPDATE cards SET ease_factor = ?, interval_days = ?, repetitions = ?, due_date = ? WHERE id = ?",
            (state.ease_factor, state.interval_days, state.repetitions,
             state.due_date.isoformat() if state.due_date else None, card_id),
        )

    def count_due(self, today: date) -> int:
        return self._scalar("SELECT COUNT(*) FROM cards WHERE due_date <= ?", (today.isoformat(),))

    def count_new(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM cards WHERE due_date IS NULL")

    def count_all(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM cards")

    def _card(self, sql: str, params: tuple = ()) -> Card | None:
        row = self._fetch_one(sql, params)
        return _to_card(row) if row else None


class SqliteReviewLog(SqliteRepository, ReviewLog):
    def add(self, review: Review) -> None:
        self._execute(
            "INSERT INTO reviews (card_id, reviewed_at, quality, resulting_interval, resulting_ease) "
            "VALUES (?, ?, ?, ?, ?)",
            (review.card_id, review.reviewed_at.isoformat(timespec="seconds"), review.quality,
             review.resulting_interval, review.resulting_ease),
        )

    def count_reviews_on(self, day: date) -> int:
        return self._scalar("SELECT COUNT(*) FROM reviews WHERE date(reviewed_at) = ?", (day.isoformat(),))

    def count_first_reviews_on(self, day: date) -> int:
        return self._scalar(
            "SELECT COUNT(*) FROM (SELECT card_id, MIN(reviewed_at) AS first FROM reviews GROUP BY card_id) "
            "WHERE date(first) = ?",
            (day.isoformat(),),
        )


class SqliteSettingsStore(SqliteRepository, SettingsStore):
    def get(self, key: str) -> str | None:
        row = self._fetch_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        self._execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def _to_card(row: sqlite3.Row) -> Card:
    due = row["due_date"]
    state = CardState(row["ease_factor"], row["interval_days"], row["repetitions"],
                      date.fromisoformat(due) if due else None)
    return Card(row["id"], row["card_type"], row["word_id"], row["sentence_id"], state)
