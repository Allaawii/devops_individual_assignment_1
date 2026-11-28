"""Content storage: abstract interfaces, plus their SQL Server implementations.

Services depend on the abstract classes, so tests can pass in-memory fakes.
Repositories never commit; the request teardown in content.db does.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, NamedTuple

from content.db import MssqlRepository
from content.models import USER_SOURCE, Sentence, Word

SENTENCE_COLUMNS = "s.id, s.spanish_text, s.english_text, s.grammar_note, s.source, s.created_at, s.level"
WORD_COLUMNS = "w.id, w.headword, w.meaning, w.frequency_rank"


class NewSentence(NamedTuple):
    """A sentence that is ready to insert (used by the batched seed import)."""

    spanish_text: str
    english_text: str
    grammar_note: str | None
    source: str
    created_at: str
    level: int | None = None   # the seed's difficulty band, 0-4


class SentenceRepository(ABC):
    """Stores sentences."""

    @abstractmethod
    def add(self, *, spanish_text: str, english_text: str, grammar_note: str | None,
            source: str, created_at: str) -> Sentence:
        """Insert a sentence and return it with its new id."""

    @abstractmethod
    def add_many(self, sentences: list[NewSentence]) -> None:
        """Insert many sentences at once; their ids follow the list order."""

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

    @abstractmethod
    def seed(self) -> list[Sentence]:
        """Every sentence that came with the app (not added by the learner), easiest first."""

    @abstractmethod
    def ids_after(self, after_id: int, limit: int) -> list[int]:
        """Up to `limit` sentence ids greater than `after_id`, in ascending order."""

    @abstractmethod
    def ids_by_text(self) -> dict[str, int]:
        """The id of every sentence, keyed by its Spanish text."""


class WordRepository(ABC):
    """Stores words and which sentences they appear in."""

    @abstractmethod
    def get_or_create(self, headword: str) -> Word:
        """Return the word with this headword, inserting it first if it is new."""

    @abstractmethod
    def add_many(self, words: list[tuple[str, int | None]]) -> None:
        """Insert many new (headword, frequency_rank) words at once; their ids follow the list order."""

    @abstractmethod
    def get(self, word_id: int) -> Word | None:
        """Return the word, or None if the id is unknown."""

    @abstractmethod
    def ids_by_headword(self) -> dict[str, int]:
        """The id of every word, keyed by its headword."""

    @abstractmethod
    def link(self, sentence_id: int, word_id: int) -> None:
        """Record that the word appears in the sentence. Linking twice is harmless."""

    @abstractmethod
    def link_many(self, links: list[tuple[int, int]]) -> None:
        """Insert many new (sentence_id, word_id) links at once."""

    @abstractmethod
    def for_sentence(self, sentence_id: int) -> list[Word]:
        """The words linked to a sentence, in id order."""

    @abstractmethod
    def word_ids_by_sentence(self, sentence_ids: list[int]) -> dict[int, list[int]]:
        """For each of the sentences, the ids of its words in id order (sentences without words are left out)."""

    @abstractmethod
    def ids_in_sentences(self, sentence_ids: list[int]) -> list[int]:
        """The ids of every word used in any of the sentences, each once, in id order."""

    @abstractmethod
    def list_page(self, limit: int, offset: int) -> list[Word]:
        """Words with no meaning first, then by frequency rank (unranked last)."""

    @abstractmethod
    def set_meaning(self, word_id: int, meaning: str | None) -> None:
        """Save the learner's meaning for a word."""


class MssqlSentenceRepository(MssqlRepository, SentenceRepository):
    def add(self, *, spanish_text: str, english_text: str, grammar_note: str | None,
            source: str, created_at: str) -> Sentence:
        row = self._fetch_one(
            "INSERT INTO sentences (spanish_text, english_text, grammar_note, source, created_at) "
            "OUTPUT INSERTED.id VALUES (%s, %s, %s, %s, %s)",
            (spanish_text, english_text, grammar_note, source, created_at),
        )
        return Sentence(row["id"], spanish_text, english_text, grammar_note, source, created_at)

    def add_many(self, sentences: list[NewSentence]) -> None:
        self._insert_many("sentences", NewSentence._fields, sentences)

    def exists(self, spanish_text: str) -> bool:
        return self._fetch_one("SELECT 1 AS found FROM sentences WHERE spanish_text = %s", (spanish_text,)) is not None

    def get(self, sentence_id: int) -> Sentence | None:
        row = self._fetch_one(f"SELECT {SENTENCE_COLUMNS} FROM sentences s WHERE s.id = %s", (sentence_id,))
        return _to_sentence(row) if row else None

    def count(self) -> int:
        return self._scalar("SELECT COUNT(*) AS n FROM sentences")

    def list_page(self, limit: int, offset: int) -> list[Sentence]:
        rows = self._fetch_all(
            f"SELECT {SENTENCE_COLUMNS} FROM sentences s ORDER BY s.id "
            "OFFSET %s ROWS FETCH NEXT %s ROWS ONLY", (offset, limit),
        )
        return [_to_sentence(row) for row in rows]

    def containing_word(self, word_id: int, limit: int) -> list[Sentence]:
        rows = self._fetch_all(
            f"SELECT TOP (%s) {SENTENCE_COLUMNS} FROM sentences s "
            "JOIN sentence_words sw ON sw.sentence_id = s.id "
            "WHERE sw.word_id = %s ORDER BY s.id",
            (limit, word_id),
        )
        return [_to_sentence(row) for row in rows]

    def seed(self) -> list[Sentence]:
        # The seed is imported in difficulty order, so id order is easiest first within each level.
        rows = self._fetch_all(f"SELECT {SENTENCE_COLUMNS} FROM sentences s WHERE s.source <> %s ORDER BY s.id",
                               (USER_SOURCE,))
        return [_to_sentence(row) for row in rows]

    def ids_after(self, after_id: int, limit: int) -> list[int]:
        rows = self._fetch_all("SELECT TOP (%s) id FROM sentences WHERE id > %s ORDER BY id", (limit, after_id))
        return [row["id"] for row in rows]

    def ids_by_text(self) -> dict[str, int]:
        return {row["spanish_text"]: row["id"] for row in self._fetch_all("SELECT id, spanish_text FROM sentences")}


class MssqlWordRepository(MssqlRepository, WordRepository):
    def get_or_create(self, headword: str) -> Word:
        self._execute("INSERT INTO words (headword) SELECT %s "
                      "WHERE NOT EXISTS (SELECT 1 FROM words WHERE headword = %s)", (headword, headword))
        return _to_word(self._fetch_one(f"SELECT {WORD_COLUMNS} FROM words w WHERE w.headword = %s", (headword,)))

    def add_many(self, words: list[tuple[str, int | None]]) -> None:
        self._insert_many("words", ("headword", "frequency_rank"), words)

    def get(self, word_id: int) -> Word | None:
        row = self._fetch_one(f"SELECT {WORD_COLUMNS} FROM words w WHERE w.id = %s", (word_id,))
        return _to_word(row) if row else None

    def ids_by_headword(self) -> dict[str, int]:
        return {row["headword"]: row["id"] for row in self._fetch_all("SELECT id, headword FROM words")}

    def link(self, sentence_id: int, word_id: int) -> None:
        self._execute(
            "INSERT INTO sentence_words (sentence_id, word_id) SELECT %s, %s WHERE NOT EXISTS "
            "(SELECT 1 FROM sentence_words WHERE sentence_id = %s AND word_id = %s)",
            (sentence_id, word_id, sentence_id, word_id),
        )

    def link_many(self, links: list[tuple[int, int]]) -> None:
        self._insert_many("sentence_words", ("sentence_id", "word_id"), links)

    def for_sentence(self, sentence_id: int) -> list[Word]:
        rows = self._fetch_all(
            f"SELECT {WORD_COLUMNS} FROM words w "
            "JOIN sentence_words sw ON sw.word_id = w.id "
            "WHERE sw.sentence_id = %s ORDER BY w.id",
            (sentence_id,),
        )
        return [_to_word(row) for row in rows]

    def word_ids_by_sentence(self, sentence_ids: list[int]) -> dict[int, list[int]]:
        rows = self._fetch_all_in("SELECT sentence_id, word_id FROM sentence_words "
                                  "WHERE sentence_id IN ({ids}) ORDER BY sentence_id, word_id", sentence_ids)
        grouped: dict[int, list[int]] = {}
        for row in rows:
            grouped.setdefault(row["sentence_id"], []).append(row["word_id"])
        return grouped

    def ids_in_sentences(self, sentence_ids: list[int]) -> list[int]:
        rows = self._fetch_all_in("SELECT DISTINCT word_id FROM sentence_words WHERE sentence_id IN ({ids})",
                                  sentence_ids)
        return sorted({row["word_id"] for row in rows})  # a set, because batches can repeat a word

    def list_page(self, limit: int, offset: int) -> list[Word]:
        rows = self._fetch_all(
            f"SELECT {WORD_COLUMNS} FROM words w ORDER BY "
            "CASE WHEN w.meaning IS NULL OR w.meaning = N'' THEN 0 ELSE 1 END, "   # no meaning yet first
            "CASE WHEN w.frequency_rank IS NULL THEN 1 ELSE 0 END, "               # unranked last
            "w.frequency_rank, w.headword "
            "OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            (offset, limit),
        )
        return [_to_word(row) for row in rows]

    def set_meaning(self, word_id: int, meaning: str | None) -> None:
        self._execute("UPDATE words SET meaning = %s WHERE id = %s", (meaning, word_id))


def _to_sentence(row: dict[str, Any]) -> Sentence:
    return Sentence(**{**row, "created_at": _iso(row["created_at"])})


def _to_word(row: dict[str, Any]) -> Word:
    return Word(**row)


def _iso(value: datetime | str) -> str:
    """DATETIME2 values come back as datetime objects; the API sends them as ISO-8601 text."""
    return value.isoformat(timespec="seconds") if isinstance(value, datetime) else value
