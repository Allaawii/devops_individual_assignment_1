"""Tests for ReviewService, using fake repositories, a fake content service and a stub strategy."""

from datetime import date, datetime, timedelta

import pytest

from scheduler.algorithms import AGAIN, EASY, GOOD, HARD, SchedulingStrategy, SM2Strategy
from scheduler.content_client import ContentUnavailable, Placement
from scheduler.models import SENTENCE_CARD, WORD_CARD, CardState
from scheduler.service import KNOWN_FIRST_CHECK_DAYS, PULL_SIZE, ReviewService
from tests.fakes import FakeSettingsStore

TODAY = date(2026, 11, 17)
NOW = datetime(2026, 11, 17, 18, 0, 0)
YESTERDAY_NOW = NOW - timedelta(days=1)


class StubStrategy(SchedulingStrategy):
    """Always returns the same state and remembers what it was asked."""

    RESULT = CardState(ease_factor=9.9, interval_days=42, repetitions=7, due_date=TODAY + timedelta(days=42))

    def __init__(self) -> None:
        self.calls: list[tuple[CardState, int, date]] = []

    def next_state(self, state: CardState, quality: int, today: date) -> CardState:
        self.calls.append((state, quality, today))
        return self.RESULT


def _service(cards, log, content, strategy=None, limit=15, settings=None) -> ReviewService:
    return ReviewService(cards, log, settings or FakeSettingsStore(), strategy or SM2Strategy(), limit, content)


def _make_due(cards, card_id: int, due: date) -> None:
    cards.save_state(card_id, CardState(interval_days=1, repetitions=1, due_date=due))


def _targets(cards) -> list[tuple[str, int | None]]:
    return [(c.card_type, c.sentence_id if c.card_type == SENTENCE_CARD else c.word_id) for c in cards.rows.values()]


# ----- the pull -----

def test_first_card_pulls_sentences_from_content_in_introduction_order(service, cards, content):
    content.sentences = {1: [10, 11], 2: [11, 12]}
    assert service.next_card(TODAY).id == 1
    assert content.calls == [("feed", 0, PULL_SIZE)]
    assert _targets(cards) == [(SENTENCE_CARD, 1), (WORD_CARD, 10), (WORD_CARD, 11),
                               (SENTENCE_CARD, 2), (WORD_CARD, 12)]         # word 11 gets one card only


def test_no_pull_while_new_cards_are_stored(service, content):
    content.sentences = {1: [10]}
    service.next_card(TODAY)
    service.next_card(TODAY)
    assert [call[0] for call in content.calls] == ["feed"]


def test_next_pull_starts_after_the_highest_sentence_with_a_card(service, cards, content):
    content.sentences = {1: [10], 2: [], 5: [11]}
    service.next_card(TODAY)
    for card in list(cards.rows.values()):
        service.review(card.id, GOOD, NOW)            # every stored card is now learned
    content.sentences[9] = [12]
    service.next_card(TODAY)
    assert content.calls[-1] == ("feed", 5, PULL_SIZE)
    assert cards.max_sentence_id() == 9


def test_no_pull_when_the_daily_limit_is_used_up(cards, log, content):
    service = _service(cards, log, content, limit=1)
    content.sentences = {1: [], 2: []}
    service.review(service.next_card(TODAY).id, GOOD, NOW)
    content.calls.clear()
    assert service.next_card(TODAY) is None
    assert content.calls == []


def test_content_with_nothing_new_means_nothing_to_review(service, content):
    assert service.next_card(TODAY) is None
    assert content.calls == [("feed", 0, PULL_SIZE)]


def test_pull_while_content_is_down_raises_content_unavailable(service, content):
    content.down = True
    with pytest.raises(ContentUnavailable):
        service.next_card(TODAY)


def test_due_cards_are_chosen_without_asking_content(service, cards, content):
    content.sentences = {1: [10]}
    service.next_card(TODAY)
    _make_due(cards, 2, TODAY)
    content.down = True
    assert service.next_card(TODAY).id == 2


# ----- next_card -----

def test_due_review_comes_before_new_cards(service, cards, content):
    content.sentences = {1: [10, 11]}
    service.next_card(TODAY)
    _make_due(cards, 3, TODAY)
    assert service.next_card(TODAY).id == 3


def test_longest_overdue_card_comes_first(service, cards, content):
    content.sentences = {1: [10, 11]}
    service.next_card(TODAY)
    _make_due(cards, 2, TODAY)
    _make_due(cards, 3, TODAY - timedelta(days=2))
    assert service.next_card(TODAY).id == 3


def test_daily_new_card_limit_is_respected(cards, log, content):
    service = _service(cards, log, content, limit=2)
    content.sentences = {1: [10, 11, 12]}
    service.review(service.next_card(TODAY).id, GOOD, NOW)
    service.review(service.next_card(TODAY).id, GOOD, NOW)
    assert cards.count_new() == 2
    assert service.next_card(TODAY) is None


def test_reviewing_an_old_card_does_not_use_up_the_new_card_limit(cards, log, content):
    service = _service(cards, log, content, limit=1)
    content.sentences = {1: [10]}
    service.next_card(YESTERDAY_NOW.date())
    service.review(1, GOOD, YESTERDAY_NOW)      # introduced yesterday
    service.review(1, GOOD, NOW)                # reviewed again today
    assert service.next_card(TODAY).id == 2


# ----- next_review: the card with its text -----

def test_sentence_card_comes_with_its_text_previews_and_numbers(service, content):
    content.sentences = {1: [10]}
    screen = service.next_review(TODAY)
    assert screen.card.id == 1
    assert screen.content["sentence"]["id"] == 1
    assert screen.intervals == {AGAIN: 1, HARD: 1, GOOD: 1, EASY: 1}
    assert (screen.stats.total_cards, screen.stats.new_left_today) == (2, 15)
    assert content.calls[-1] == ("sentence", 1)


def test_word_card_comes_with_the_word_text(service, cards, content):
    content.sentences = {1: [10]}
    service.next_card(TODAY)
    service.review(1, GOOD, NOW)
    screen = service.next_review(TODAY)
    assert (screen.card.card_type, screen.content["word"]["id"]) == (WORD_CARD, 10)
    assert content.calls[-1] == ("word", 10)


def test_nothing_to_review_gives_none(service):
    assert service.next_review(TODAY) is None


def test_card_text_while_content_is_down_raises_content_unavailable(service, cards, content):
    content.sentences = {1: []}
    service.next_card(TODAY)
    _make_due(cards, 1, TODAY)
    content.down = True
    with pytest.raises(ContentUnavailable):
        service.next_review(TODAY)


# ----- review -----

def test_review_saves_the_new_state_and_logs_it(service, cards, log, content):
    content.sentences = {1: []}
    service.next_card(TODAY)
    new_state = service.review(1, GOOD, NOW)
    assert cards.get(1).state == new_state
    assert new_state.due_date == TODAY + timedelta(days=1)
    [entry] = log.reviews
    assert (entry.card_id, entry.reviewed_at, entry.quality) == (1, NOW, GOOD)
    assert (entry.resulting_interval, entry.resulting_ease) == (1, 2.5)


def test_review_uses_the_injected_strategy(cards, log, content):
    stub = StubStrategy()
    service = _service(cards, log, content, strategy=stub)
    content.sentences = {1: []}
    service.next_card(TODAY)
    assert service.review(1, GOOD, NOW) == StubStrategy.RESULT
    assert stub.calls == [(CardState(), GOOD, TODAY)]


def test_review_needs_no_content(service, cards, content):
    content.sentences = {1: []}
    service.next_card(TODAY)
    content.down = True
    service.review(1, GOOD, NOW)
    assert cards.get(1).state.repetitions == 1


def test_reviewing_an_unknown_card_raises_lookup_error(service):
    with pytest.raises(LookupError):
        service.review(99, GOOD, NOW)


def test_invalid_quality_saves_and_logs_nothing(service, cards, log, content):
    content.sentences = {1: []}
    service.next_card(TODAY)
    with pytest.raises(ValueError):
        service.review(1, 9, NOW)
    assert cards.get(1).state == CardState()
    assert log.reviews == []


# ----- daily goal -----

def test_default_limit_applies_until_a_goal_is_chosen(service):
    assert service.daily_goal() is None
    assert service.new_cards_per_day() == service.default_new_cards_per_day() == 15


def test_chosen_goal_replaces_the_default_and_is_stored(service, settings):
    service.set_daily_goal(20)
    assert service.daily_goal() == 20
    assert service.new_cards_per_day() == 20
    assert settings.values == {"new_cards_per_day": "20"}


@pytest.mark.parametrize("goal", [0, 101, -5])
def test_goal_outside_1_to_100_is_rejected(service, goal):
    with pytest.raises(ValueError):
        service.set_daily_goal(goal)
    assert service.daily_goal() is None


# ----- preview and stats -----

def test_preview_shows_each_rating_interval_without_saving(service, cards, log, content):
    content.sentences = {1: []}
    service.next_card(TODAY)
    learned = CardState(ease_factor=2.5, interval_days=6, repetitions=2, due_date=TODAY)
    cards.save_state(1, learned)
    assert service.preview_intervals(cards.get(1), TODAY) == {AGAIN: 1, HARD: 15, GOOD: 15, EASY: 15}
    assert cards.get(1).state == learned
    assert log.reviews == []


def test_stats_use_only_the_schedulers_own_data(cards, log, content):
    service = _service(cards, log, content, limit=2)
    content.sentences = {1: [10, 11, 12]}           # 4 cards once pulled
    service.review(service.next_card(TODAY).id, GOOD, NOW)
    _make_due(cards, 2, TODAY)
    content.down = True
    stats = service.stats(TODAY)
    assert (stats.due_now, stats.new_left_today, stats.reviewed_today, stats.total_cards) == (1, 1, 1, 4)


def test_new_left_today_is_the_daily_allowance_even_before_any_pull(service):
    assert service.stats(TODAY).new_left_today == 15


# ----- placement -----

def test_level_is_none_until_the_learner_is_placed(service):
    assert service.level() is None


def test_placing_creates_known_cards_and_stores_the_level(service, cards, content):
    content.placement = Placement(2, "Elementary", [1, 2], [10, 11])
    outcome = service.place_learner({"q1": "a"}, TODAY)
    assert (outcome.level, outcome.level_name, outcome.skipped) == (2, "Elementary", 4)
    assert service.level() == (2, "Elementary")
    assert content.calls == [("score", {"q1": "a"})]
    assert cards.count_new() == 0
    assert cards.max_sentence_id() == 2              # the pull continues after the known material


def test_skipped_cards_come_back_for_a_check_spread_over_the_months(service, cards, content):
    content.placement = Placement(1, "Beginner", [1], [10, 11])
    service.place_learner({}, TODAY)
    due_dates = [card.state.due_date for card in cards.rows.values()]
    assert due_dates == [TODAY + timedelta(days=KNOWN_FIRST_CHECK_DAYS + n) for n in range(3)]
    assert all(card.state.repetitions == 2 for card in cards.rows.values())
    assert service.stats(TODAY).due_now == 0


def test_placing_moves_existing_new_cards_but_never_reviewed_ones(service, cards, content):
    content.sentences = {1: [10]}
    service.next_card(TODAY)                          # cards 1 (sentence 1) and 2 (word 10)
    service.review(1, AGAIN, NOW)
    reviewed = cards.get(1).state
    content.placement = Placement(1, "Beginner", [1], [10])
    assert service.place_learner({}, TODAY).skipped == 1   # only the word card
    assert cards.get(1).state == reviewed
    assert cards.count_all() == 2


def test_skipping_the_quiz_needs_no_content(service, cards, content):
    content.down = True
    outcome = service.place_learner(None, TODAY)
    assert (outcome.level, outcome.level_name, outcome.skipped) == (0, "Starter", 0)
    assert service.level() == (0, "Starter")
    assert cards.count_all() == 0


def test_placing_while_content_is_down_saves_nothing(service, settings, content):
    content.down = True
    with pytest.raises(ContentUnavailable):
        service.place_learner({"q1": "a"}, TODAY)
    assert settings.values == {}
