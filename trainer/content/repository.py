"""Content storage: abstract interfaces, plus their SQLite implementations.

Services depend on the abstract classes, so tests can pass in-memory fakes.
Repositories never commit; the request teardown in trainer.db does.
"""

import sqlite3
from abc import ABC, abstractmethod

from trainer.content.models import Sentence, Word
from trainer.db import SqliteRepository

SENTENCE_COLUMNS = "s.id, s.spanish_text, s.english_text, s.grammar_note, s.source, s.created_at"
WORD_COLUMNS = "w.id, w.headword, w.meaning, w.frequency_rank"


class SentenceRepository(ABC):
    """Stores sentences."""

    @abstractmethod
    def add(self, *, spanish_text: str, english_text: str, grammar_note: str | None,
            source: str, created_at: str) -> Sentence:
        """Insert a sentence and return it with its new id."""

    @abstractmethod
    def exists(self, spanish_text: str) -> bool:
        """True if a sentence with exactly this Spanish text is stored."""

    @abstractmethod
    def get(self, sentence_id: int) -> Sentence | None:
        """Return the sentence, or None if the id is unknown."""

    @abstractmethod
    def count(self) -> int:
        """Number of stored sentences."""

    @abstractmethod
    def list_page(self, limit: int, offset: int) -> list[Sentence]:
        """Sentences in id order, skipping `offset` and returning at most `limit`."""

    @abstractmethod
    def containing_word(self, word_id: int, limit: int) -> list[Sentence]:
        """Up to `limit` sentences that contain the word, in id order."""


class WordRepository(ABC):
    """Stores words and which sentences they appear in."""

    @abstractmethod
    def get_or_create(self, headword: str) -> Word:
        """Return the word with this headword, inserting it first if it is new."""

    @abstractmethod
    def get(self, word_id: int) -> Word | None:
        """Return the word, or None if the id is unknown."""

    @abstractmethod
    def link(self, sentence_id: int, word_id: int) -> None:
        """Record that the word appears in the sentence. Linking twice is harmless."""

    @abstractmethod
    def for_sentence(self, sentence_id: int) -> list[Word]:
        """The words linked to a sentence, in id order."""

    @abstractmethod
    def list_page(self, limit: int, offset: int) -> list[Word]:
        """Words with no meaning first, then by frequency rank (unranked last)."""

    @abstractmethod
    def set_meaning(self, word_id: int, meaning: str | None) -> None:
        """Save the learner's meaning for a word."""

    @abstractmethod
    def set_frequency_ranks(self, ranks: dict[str, int]) -> None:
        """Set the rank of each headword, creating words that don't exist yet."""


class SqliteSentenceRepository(SqliteRepository, SentenceRepository):
    def add(self, *, spanish_text: str, english_text: str, grammar_note: str | None,
            source: str, created_at: str) -> Sentence:
        cursor = self._execute(
            "INSERT INTO sentences (spanish_text, english_text, grammar_note, source, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (spanish_text, english_text, grammar_note, source, created_at),
        )
        return Sentence(cursor.lastrowid, spanish_text, english_text, grammar_note, source, created_at)

    def exists(self, spanish_text: str) -> bool:
        return self._fetch_one("SELECT 1 FROM sentences WHERE spanish_text = ?", (spanish_text,)) is not None

    def get(self, sentence_id: int) -> Sentence | None:
        row = self._fetch_one(f"SELECT {SENTENCE_COLUMNS} FROM sentences s WHERE s.id = ?", (sentence_id,))
        return _to_sentence(row) if row else None

    def count(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM sentences")

    def list_page(self, limit: int, offset: int) -> list[Sentence]:
        rows = self._fetch_all(
            f"SELECT {SENTENCE_COLUMNS} FROM sentences s ORDER BY s.id LIMIT ? OFFSET ?", (limit, offset)
        )
        return [_to_sentence(row) for row in rows]

    def containing_word(self, word_id: int, limit: int) -> list[Sentence]:
        rows = self._fetch_all(
            f"SELECT {SENTENCE_COLUMNS} FROM sentences s "
            "JOIN sentence_words sw ON sw.sentence_id = s.id "
            "WHERE sw.word_id = ? ORDER BY s.id LIMIT ?",
            (word_id, limit),
        )
        return [_to_sentence(row) for row in rows]


class SqliteWordRepository(SqliteRepository, WordRepository):
    def get_or_create(self, headword: str) -> Word:
        self._execute("INSERT OR IGNORE INTO words (headword) VALUES (?)", (headword,))
        return _to_word(self._fetch_one(f"SELECT {WORD_COLUMNS} FROM words w WHERE w.headword = ?", (headword,)))

    def get(self, word_id: int) -> Word | None:
        row = self._fetch_one(f"SELECT {WORD_COLUMNS} FROM words w WHERE w.id = ?", (word_id,))
        return _to_word(row) if row else None

    def link(self, sentence_id: int, word_id: int) -> None:
        self._execute(
            "INSERT OR IGNORE INTO sentence_words (sentence_id, word_id) VALUES (?, ?)", (sentence_id, word_id)
        )

    def for_sentence(self, sentence_id: int) -> list[Word]:
        rows = self._fetch_all(
            f"SELECT {WORD_COLUMNS} FROM words w "
            "JOIN sentence_words sw ON sw.word_id = w.id "
            "WHERE sw.sentence_id = ? ORDER BY w.id",
            (sentence_id,),
        )
        return [_to_word(row) for row in rows]

    def list_page(self, limit: int, offset: int) -> list[Word]:
        rows = self._fetch_all(
            f"SELECT {WORD_COLUMNS} FROM words w "
            "ORDER BY (w.meaning IS NULL OR w.meaning = '') DESC, "
            "w.frequency_rank IS NULL, w.frequency_rank, w.headword "
            "LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [_to_word(row) for row in rows]

    def set_meaning(self, word_id: int, meaning: str | None) -> None:
        self._execute("UPDATE words SET meaning = ? WHERE id = ?", (meaning, word_id))

    def set_frequency_ranks(self, ranks: dict[str, int]) -> None:
        self._execute_many(
            "INSERT INTO words (headword, frequency_rank) VALUES (?, ?) "
            "ON CONFLICT(headword) DO UPDATE SET frequency_rank = excluded.frequency_rank",
            ranks.items(),
        )


def _to_sentence(row: sqlite3.Row) -> Sentence:
    return Sentence(**dict(row))


def _to_word(row: sqlite3.Row) -> Word:
    return Word(**dict(row))
