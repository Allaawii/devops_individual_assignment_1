"""In-memory stand-ins for the repositories, so service tests need no database."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime

from trainer.content.models import Sentence, Word
from trainer.content.repository import SentenceRepository, WordRepository
from trainer.scheduler.models import SENTENCE_CARD, WORD_CARD, Card, CardState, Review
from trainer.scheduler.repository import CardRepository, ReviewLog, SettingsStore


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


class FakeCardRepository(CardRepository):
    def __init__(self) -> None:
        self.rows: dict[int, Card] = {}

    def ensure_sentence_card(self, sentence_id: int) -> None:
        if not any(card.sentence_id == sentence_id for card in self.rows.values()):
            self._add(SENTENCE_CARD, None, sentence_id)

    def ensure_word_cards(self, word_ids: Iterable[int]) -> None:
        for word_id in word_ids:
            if not any(card.word_id == word_id for card in self.rows.values()):
                self._add(WORD_CARD, word_id, None)

    def get(self, card_id: int) -> Card | None:
        return self.rows.get(card_id)

    def next_due(self, today: date) -> Card | None:
        return min(self._due(today), key=lambda card: (card.state.due_date, card.id), default=None)

    def next_new(self) -> Card | None:
        return min(self._new(), key=lambda card: card.id, default=None)

    def save_state(self, card_id: int, state: CardState) -> None:
        self.rows[card_id] = replace(self.rows[card_id], state=state)

    def count_due(self, today: date) -> int:
        return len(self._due(today))

    def count_new(self) -> int:
        return len(self._new())

    def count_all(self) -> int:
        return len(self.rows)

    def _add(self, card_type: str, word_id: int | None, sentence_id: int | None) -> None:
        card = Card(len(self.rows) + 1, card_type, word_id, sentence_id, CardState())
        self.rows[card.id] = card

    def _due(self, today: date) -> list[Card]:
        return [c for c in self.rows.values() if c.state.due_date is not None and c.state.due_date <= today]

    def _new(self) -> list[Card]:
        return [c for c in self.rows.values() if c.state.due_date is None]


class FakeReviewLog(ReviewLog):
    def __init__(self) -> None:
        self.reviews: list[Review] = []

    def add(self, review: Review) -> None:
        self.reviews.append(review)

    def count_reviews_on(self, day: date) -> int:
        return sum(1 for review in self.reviews if review.reviewed_at.date() == day)

    def count_first_reviews_on(self, day: date) -> int:
        first: dict[int, datetime] = {}
        for review in self.reviews:
            if review.card_id not in first or review.reviewed_at < first[review.card_id]:
                first[review.card_id] = review.reviewed_at
        return sum(1 for moment in first.values() if moment.date() == day)


class FakeSettingsStore(SettingsStore):
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value
