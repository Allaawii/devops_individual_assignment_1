"""Read-only records for the content domain. Field names match the table columns."""

import math
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

USER_SOURCE = "user"  # `source` of sentences the learner typed in; seed sentences store their attribution


@dataclass(frozen=True)
class Sentence:
    id: int
    spanish_text: str
    english_text: str
    grammar_note: str | None
    source: str
    created_at: str


@dataclass(frozen=True)
class Word:
    id: int
    headword: str
    meaning: str | None
    frequency_rank: int | None


@dataclass(frozen=True)
class SentenceDetail:
    """A sentence together with the words extracted from it."""

    sentence: Sentence
    words: list[Word]

    def key_words(self, limit: int = 3) -> list[Word]:
        """The `limit` rarest words: the ones that carry the meaning, not él or está.

        Unranked words (only in the learner's own sentences) count as rarest; ties keep sentence order.
        """
        return sorted(self.words, key=lambda word: word.frequency_rank or math.inf, reverse=True)[:limit]


@dataclass(frozen=True)
class Page(Generic[T]):
    """One page of a longer list of sentences or words."""

    items: list[T]
    number: int     # 1-based
    has_next: bool
