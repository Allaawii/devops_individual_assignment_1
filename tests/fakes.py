"""In-memory stand-ins for the repositories, so service tests need no database."""

from dataclasses import replace

from trainer.content.models import Sentence, Word
from trainer.content.repository import SentenceRepository, WordRepository


class FakeSentenceRepository(SentenceRepository):
    def __init__(self) -> None:
        self.rows: dict[int, Sentence] = {}
        self.links: set[tuple[int, int]] = set()  # (sentence_id, word_id), shared with FakeWordRepository

    def add(self, *, spanish_text, english_text, grammar_note, source, created_at) -> Sentence:
        sentence = Sentence(len(self.rows) + 1, spanish_text, english_text, grammar_note, source, created_at)
        self.rows[sentence.id] = sentence
        return sentence

    def exists(self, spanish_text: str) -> bool:
        return any(s.spanish_text == spanish_text for s in self.rows.values())

    def get(self, sentence_id: int) -> Sentence | None:
        return self.rows.get(sentence_id)

    def count(self) -> int:
        return len(self.rows)

    def list_page(self, limit: int, offset: int) -> list[Sentence]:
        return sorted(self.rows.values(), key=lambda s: s.id)[offset:offset + limit]

    def containing_word(self, word_id: int, limit: int) -> list[Sentence]:
        ids = sorted(s_id for s_id, w_id in self.links if w_id == word_id)
        return [self.rows[s_id] for s_id in ids[:limit]]


class FakeWordRepository(WordRepository):
    def __init__(self, links: set[tuple[int, int]]) -> None:
        self.rows: dict[int, Word] = {}
        self.links = links

    def get_or_create(self, headword: str) -> Word:
        for word in self.rows.values():
            if word.headword == headword:
                return word
        word = Word(len(self.rows) + 1, headword, None, None)
        self.rows[word.id] = word
        return word

    def get(self, word_id: int) -> Word | None:
        return self.rows.get(word_id)

    def link(self, sentence_id: int, word_id: int) -> None:
        self.links.add((sentence_id, word_id))

    def for_sentence(self, sentence_id: int) -> list[Word]:
        return [self.rows[w_id] for s_id, w_id in sorted(self.links) if s_id == sentence_id]

    def list_page(self, limit: int, offset: int) -> list[Word]:
        return sorted(self.rows.values(), key=lambda w: w.id)[offset:offset + limit]

    def set_meaning(self, word_id: int, meaning: str | None) -> None:
        self.rows[word_id] = replace(self.rows[word_id], meaning=meaning)

    def set_frequency_ranks(self, ranks: dict[str, int]) -> None:
        for headword, rank in ranks.items():
            word = self.get_or_create(headword)
            self.rows[word.id] = replace(word, frequency_rank=rank)
