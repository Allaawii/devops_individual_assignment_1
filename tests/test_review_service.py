"""Tests for ReviewService, using fake repositories and a stub strategy."""

from datetime import date, datetime, timedelta

import pytest

from tests.fakes import FakeCardRepository, FakeReviewLog
from trainer.scheduler.algorithms import GOOD, SchedulingStrategy, SM2Strategy
from trainer.scheduler.models import SENTENCE_CARD, WORD_CARD, CardState
from trainer.scheduler.service import ReviewService

TODAY = date(2026, 9, 30)
NOW = datetime(2026, 9, 30, 18, 0, 0)
YESTERDAY_NOW = NOW - timedelta(days=1)


class StubStrategy(SchedulingStrategy):
    """Always returns the same state and remembers what it was asked."""

    RESULT = CardState(ease_factor=9.9, interval_days=42, repetitions=7, due_date=TODAY + timedelta(days=42))

    def __init__(self) -> None:
        self.calls: list[tuple[CardState, int, date]] = []

    def next_state(self, state: CardState, quality: int, today: date) -> CardState:
        self.calls.append((state, quality, today))
        return self.RESULT


@pytest.fixture
def cards() -> FakeCardRepository:
    return FakeCardRepository()


@pytest.fixture
def log() -> FakeReviewLog:
    return FakeReviewLog()


def _service(cards, log, strategy=None, limit=15) -> ReviewService:
    return ReviewService(cards, log, strategy or SM2Strategy(), new_cards_per_day=limit)


@pytest.fixture
def service(cards, log) -> ReviewService:
    return _service(cards, log)


def _make_due(cards: FakeCardRepository, card_id: int, due: date) -> None:
    cards.save_state(card_id, CardState(interval_days=1, repetitions=1, due_date=due))


# ----- on_sentence_added (the observer callback) -----

def test_new_sentence_gets_one_sentence_card_then_word_cards(service, cards):
    service.on_sentence_added(1, [10, 11])
    created = [(c.card_type, c.sentence_id, c.word_id) for c in cards.rows.values()]
    assert created == [(SENTENCE_CARD, 1, None), (WORD_CARD, None, 10), (WORD_CARD, None, 11)]


def test_calling_twice_creates_no_duplicates(service, cards):
    service.on_sentence_added(1, [10, 11])
    service.on_sentence_added(1, [10, 11])
    assert cards.count_all() == 3


def test_word_shared_by_two_sentences_gets_one_card(service, cards):
    service.on_sentence_added(1, [10])
    service.on_sentence_added(2, [10, 12])
    assert [c.word_id for c in cards.rows.values() if c.card_type == WORD_CARD] == [10, 12]


def test_new_cards_start_with_no_due_date(service, cards):
    service.on_sentence_added(1, [10])
    assert all(card.state == CardState() for card in cards.rows.values())


# ----- next_card -----

def test_due_review_comes_before_new_cards(service, cards):
    service.on_sentence_added(1, [10, 11])
    _make_due(cards, 3, TODAY)
    assert service.next_card(TODAY).id == 3


def test_longest_overdue_card_comes_first(service, cards):
    service.on_sentence_added(1, [10, 11])
    _make_due(cards, 2, TODAY)
    _make_due(cards, 3, TODAY - timedelta(days=2))
    assert service.next_card(TODAY).id == 3


def test_card_due_in_the_future_is_not_shown(service, cards):
    service.on_sentence_added(1, [])
    _make_due(cards, 1, TODAY + timedelta(days=1))
    assert service.next_card(TODAY) is None


def test_new_cards_come_in_id_order(service):
    service.on_sentence_added(1, [10, 11])
    assert service.next_card(TODAY).id == 1


def test_no_cards_means_nothing_to_review(service):
    assert service.next_card(TODAY) is None


def test_daily_new_card_limit_is_respected(cards, log):
    service = _service(cards, log, limit=2)
    service.on_sentence_added(1, [10, 11, 12])
    service.review(1, GOOD, NOW)
    service.review(2, GOOD, NOW)
    assert cards.count_new() == 2
    assert service.next_card(TODAY) is None


def test_reviewing_an_old_card_does_not_use_up_the_new_card_limit(cards, log):
    service = _service(cards, log, limit=1)
    service.on_sentence_added(1, [10])
    service.review(1, GOOD, YESTERDAY_NOW)  # introduced yesterday
    service.review(1, GOOD, NOW)            # reviewed again today
    assert service.next_card(TODAY).id == 2


# ----- review -----

def test_review_saves_the_new_state_and_logs_it(service, cards, log):
    service.on_sentence_added(1, [])
    new_state = service.review(1, GOOD, NOW)
    assert cards.get(1).state == new_state
    assert new_state.due_date == TODAY + timedelta(days=1)
    [entry] = log.reviews
    assert (entry.card_id, entry.reviewed_at, entry.quality) == (1, NOW, GOOD)
    assert (entry.resulting_interval, entry.resulting_ease) == (1, 2.5)


def test_review_uses_the_injected_strategy(cards, log):
    stub = StubStrategy()
    service = _service(cards, log, strategy=stub)
    service.on_sentence_added(1, [])
    assert service.review(1, GOOD, NOW) == StubStrategy.RESULT
    assert stub.calls == [(CardState(), GOOD, TODAY)]


def test_reviewing_an_unknown_card_raises_lookup_error(service):
    with pytest.raises(LookupError):
        service.review(99, GOOD, NOW)


def test_invalid_quality_saves_and_logs_nothing(service, cards, log):
    service.on_sentence_added(1, [])
    with pytest.raises(ValueError):
        service.review(1, 9, NOW)
    assert cards.get(1).state == CardState()
    assert log.reviews == []


# ----- stats -----

def test_stats(cards, log):
    service = _service(cards, log, limit=2)
    service.on_sentence_added(1, [10, 11, 12])  # 4 cards
    service.review(1, GOOD, NOW)               # uses 1 of today's 2 new cards; due tomorrow
    _make_due(cards, 2, TODAY)                 # pretend card 2 was reviewed before and is due
    stats = service.stats(TODAY)
    assert stats.due_now == 1
    assert stats.new_left_today == 1           # 2 new cards remain, but only 1 left in today's limit
    assert stats.reviewed_today == 1
    assert stats.total_cards == 4
