"""Read-only records for the content domain. Field names match the table columns."""

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


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


@dataclass(frozen=True)
class Page(Generic[T]):
    """One page of a longer list of sentences or words."""

    items: list[T]
    number: int     # 1-based
    has_next: bool
