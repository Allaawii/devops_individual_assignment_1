"""Scheduler storage: abstract interfaces, plus their SQL Server implementations.

Services depend on the abstract classes, so tests can pass in-memory fakes.
Repositories never commit; the request teardown in scheduler.db does.
"""

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any

from scheduler import db
from scheduler.db import MssqlRepository
from scheduler.models import SENTENCE_CARD, Card, CardState, NewCard, Review

CARD_COLUMNS = "id, card_type, word_id, sentence_id, ease_factor, interval_days, repetitions, due_date"


class CardRepository(ABC):
    """Stores cards and their scheduling state."""

    @abstractmethod
    def ensure_cards(self, cards: list[NewCard]) -> None:
        """Create, in list order, a new card for each entry whose word or sentence has none yet."""

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
    def save_states(self, states: dict[int, CardState]) -> None:
        """Store the new state of many cards at once (card id -> state)."""

    @abstractmethod
    def max_sentence_id(self) -> int:
        """The highest content sentence id that has a card, or 0: where the next pull starts."""

    @abstractmethod
    def count_due(self, today: date) -> int:
        """Reviewed cards that are due on or before `today`."""

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


class MssqlCardRepository(MssqlRepository, CardRepository):
    def ensure_cards(self, cards: list[NewCard]) -> None:
        sentence_ids = [card.sentence_id for card in cards if card.sentence_id is not None]
        word_ids = [card.word_id for card in cards if card.word_id is not None]
        have_sentences = {row["sentence_id"] for row in self._fetch_all_in(
            "SELECT sentence_id FROM cards WHERE sentence_id IN ({ids})", sentence_ids)}
        have_words = {row["word_id"] for row in self._fetch_all_in(
            "SELECT word_id FROM cards WHERE word_id IN ({ids})", word_ids)}
        missing = [card for card in dict.fromkeys(cards)   # dict.fromkeys drops repeats, keeps order
                   if (card.sentence_id not in have_sentences if card.card_type == SENTENCE_CARD
                       else card.word_id not in have_words)]
        self._insert_many("cards", NewCard._fields, missing)

    def get(self, card_id: int) -> Card | None:
        return self._card(f"SELECT {CARD_COLUMNS} FROM cards WHERE id = %s", (card_id,))

    def next_due(self, today: date) -> Card | None:
        return self._card(f"SELECT TOP 1 {CARD_COLUMNS} FROM cards WHERE due_date <= %s ORDER BY due_date, id",
                          (today.isoformat(),))

    def next_new(self) -> Card | None:
        return self._card(f"SELECT TOP 1 {CARD_COLUMNS} FROM cards WHERE due_date IS NULL ORDER BY id")

    def new_cards_for(self, sentence_ids: list[int], word_ids: list[int]) -> list[Card]:
        rows = []
        for column, ids in (("sentence_id", sentence_ids), ("word_id", word_ids)):
            # {{ids}} survives the f-string as {ids}, which _fetch_all_in fills with placeholders.
            rows += self._fetch_all_in(
                f"SELECT {CARD_COLUMNS} FROM cards WHERE due_date IS NULL AND {column} IN ({{ids}})", ids)
        return sorted((_to_card(row) for row in rows), key=lambda card: card.id)

    def save_state(self, card_id: int, state: CardState) -> None:
        self._execute(
            "UPDATE cards SET ease_factor = %s, interval_days = %s, repetitions = %s, due_date = %s WHERE id = %s",
            (*_state_values(state), card_id),
        )

    def save_states(self, states: dict[int, CardState]) -> None:
        """One UPDATE ... FROM (VALUES ...) per batch, instead of one round trip per card.

        Every state must have a due date (placement and the strategies always set one): a VALUES
        column holding only NULLs would be typed INT, which SQL Server cannot turn into a DATE.
        """
        rows = [(card_id, *_state_values(state)) for card_id, state in states.items()]
        for batch in db.batches(rows):
            row_marks = ", ".join(["(%s, %s, %s, %s, %s)"] * len(batch))
            self._execute(
                "UPDATE c SET ease_factor = v.ease_factor, interval_days = v.interval_days, "
                "repetitions = v.repetitions, due_date = v.due_date FROM cards c "
                f"JOIN (VALUES {row_marks}) AS v (id, ease_factor, interval_days, repetitions, due_date) "
                "ON v.id = c.id",
                [value for row in batch for value in row],
            )

    def max_sentence_id(self) -> int:
        return self._scalar("SELECT COALESCE(MAX(sentence_id), 0) AS n FROM cards")

    def count_due(self, today: date) -> int:
        return self._scalar("SELECT COUNT(*) AS n FROM cards WHERE due_date <= %s", (today.isoformat(),))

    def count_all(self) -> int:
        return self._scalar("SELECT COUNT(*) AS n FROM cards")

    def _card(self, sql: str, params: tuple = ()) -> Card | None:
        row = self._fetch_one(sql, params)
        return _to_card(row) if row else None


class MssqlReviewLog(MssqlRepository, ReviewLog):
    def add(self, review: Review) -> None:
        self._execute(
            "INSERT INTO reviews (card_id, reviewed_at, quality, resulting_interval, resulting_ease) "
            "VALUES (%s, %s, %s, %s, %s)",
            (review.card_id, review.reviewed_at.isoformat(timespec="seconds"), review.quality,
             review.resulting_interval, review.resulting_ease),
        )

    def count_reviews_on(self, day: date) -> int:
        return self._scalar("SELECT COUNT(*) AS n FROM reviews WHERE reviewed_at >= %s AND reviewed_at < %s",
                            _day_range(day))

    def count_first_reviews_on(self, day: date) -> int:
        return self._scalar(
            "SELECT COUNT(*) AS n FROM (SELECT card_id, MIN(reviewed_at) AS first_review FROM reviews "
            "GROUP BY card_id) AS f WHERE f.first_review >= %s AND f.first_review < %s",
            _day_range(day),
        )


class MssqlSettingsStore(MssqlRepository, SettingsStore):
    def get(self, key: str) -> str | None:
        row = self._fetch_one("SELECT setting_value FROM settings WHERE setting_key = %s", (key,))
        return row["setting_value"] if row else None

    def set(self, key: str, value: str) -> None:
        # Update the row if it is there, otherwise insert it (SQL Server has no ON CONFLICT).
        self._execute(
            "UPDATE settings SET setting_value = %s WHERE setting_key = %s; "
            "IF @@ROWCOUNT = 0 INSERT INTO settings (setting_key, setting_value) VALUES (%s, %s)",
            (value, key, key, value),
        )


def _state_values(state: CardState) -> tuple:
    return (state.ease_factor, state.interval_days, state.repetitions,
            state.due_date.isoformat() if state.due_date else None)


def _day_range(day: date) -> tuple[str, str]:
    """Midnight at the start of `day` and of the next day: reviewed_at >= start AND < end is that day."""
    return day.isoformat(), (day + timedelta(days=1)).isoformat()


def _to_date(value: date | str | None) -> date | None:
    """DATE columns come back as date objects (or text with older TDS versions)."""
    if value is None:
        return None
    if isinstance(value, datetime):      # checked first: a datetime is also a date
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _to_card(row: dict[str, Any]) -> Card:
    state = CardState(row["ease_factor"], row["interval_days"], row["repetitions"], _to_date(row["due_date"]))
    return Card(row["id"], row["card_type"], row["word_id"], row["sentence_id"], state)
