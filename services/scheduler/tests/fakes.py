"""In-memory stand-ins for the repositories and the content service, so tests need no database or network."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime
from typing import Any

from scheduler.content_client import ContentClient, ContentUnavailable, FeedItem, Placement
from scheduler.models import SENTENCE_CARD, Card, CardState, NewCard, Review
from scheduler.repository import CardRepository, ReviewLog, SettingsStore


class FakeCardRepository(CardRepository):
    def __init__(self) -> None:
        self.rows: dict[int, Card] = {}

    def ensure_cards(self, cards: list[NewCard]) -> None:
        for new in cards:
            if not any(self._same_target(card, new) for card in self.rows.values()):
                card = Card(len(self.rows) + 1, new.card_type, new.word_id, new.sentence_id, CardState())
                self.rows[card.id] = card

    def get(self, card_id: int) -> Card | None:
        return self.rows.get(card_id)

    def next_due(self, today: date) -> Card | None:
        return min(self._due(today), key=lambda card: (card.state.due_date, card.id), default=None)

    def next_new(self) -> Card | None:
        return min(self._new(), key=lambda card: card.id, default=None)

    def new_cards_for(self, sentence_ids: list[int], word_ids: list[int]) -> list[Card]:
        return [c for c in sorted(self._new(), key=lambda c: c.id)
                if c.sentence_id in sentence_ids or c.word_id in word_ids]

    def save_state(self, card_id: int, state: CardState) -> None:
        self.rows[card_id] = replace(self.rows[card_id], state=state)

    def save_states(self, states: dict[int, CardState]) -> None:
        for card_id, state in states.items():
            self.save_state(card_id, state)

    def max_sentence_id(self) -> int:
        return max((c.sentence_id for c in self.rows.values() if c.sentence_id is not None), default=0)

    def count_due(self, today: date) -> int:
        return len(self._due(today))

    def count_all(self) -> int:
        return len(self.rows)

    def count_new(self) -> int:
        """Only for tests: the real repository has no need for it any more."""
        return len(self._new())

    @staticmethod
    def _same_target(card: Card, new: NewCard) -> bool:
        if new.card_type == SENTENCE_CARD:
            return card.sentence_id == new.sentence_id
        return card.word_id == new.word_id

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


class FakeContentClient(ContentClient):
    """Plays the content service.

    `sentences` maps sentence id -> word ids (the feed serves them in id order); `placement`
    is what score() returns; set `down = True` to make every call raise ContentUnavailable.
    `calls` records every call, e.g. ("feed", 0, 20).
    """

    def __init__(self) -> None:
        self.sentences: dict[int, list[int]] = {}
        self.placement = Placement(0, "Starter", [], [])
        self.down = False
        self.calls: list[tuple] = []

    def feed(self, after_id: int, limit: int) -> list[FeedItem]:
        self._record("feed", after_id, limit)
        return [FeedItem(s_id, words) for s_id, words in sorted(self.sentences.items()) if s_id > after_id][:limit]

    def sentence(self, sentence_id: int) -> dict[str, Any]:
        self._record("sentence", sentence_id)
        return {"sentence": {"id": sentence_id, "spanish_text": f"Frase {sentence_id}"}, "words": [], "key_words": []}

    def word(self, word_id: int) -> dict[str, Any]:
        self._record("word", word_id)
        return {"word": {"id": word_id, "headword": f"palabra{word_id}"}, "examples": []}

    def score(self, answers: Mapping[str, str]) -> Placement:
        self._record("score", dict(answers))
        return self.placement

    def _record(self, *call: Any) -> None:
        self.calls.append(call)
        if self.down:
            raise ContentUnavailable(f"{call[0]}: content is down (fake)")
