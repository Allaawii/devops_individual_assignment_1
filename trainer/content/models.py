"""Read-only records for the content domain. Field names match the table columns."""

from dataclasses import dataclass


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
