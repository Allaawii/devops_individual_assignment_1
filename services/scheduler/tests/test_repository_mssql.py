"""Tests for the SQL Server repositories, each on a freshly migrated database.

Skipped when TEST_DATABASE_URL is not set; CI always sets it.
"""

import threading
from datetime import date, datetime, timedelta

import pymssql
import pytest

from scheduler import db
from scheduler.models import SENTENCE_CARD, WORD_CARD, CardState, NewCard, Review
from scheduler.repository import MssqlCardRepository, MssqlReviewLog, MssqlSettingsStore

TODAY = date(2026, 11, 17)


@pytest.fixture
def cards(conn) -> MssqlCardRepository:
    return MssqlCardRepository(lambda: conn)


@pytest.fixture
def review_log(conn) -> MssqlReviewLog:
    return MssqlReviewLog(lambda: conn)


def _sentence(sentence_id: int) -> NewCard:
    return NewCard(SENTENCE_CARD, None, sentence_id)


def _word(word_id: int) -> NewCard:
    return NewCard(WORD_CARD, word_id, None)


def _review(card_id: int, when: str) -> Review:
    return Review(card_id, datetime.fromisoformat(when), 4, 1, 2.5)


def _rows(conn) -> list[tuple]:
    cursor = conn.cursor()
    cursor.execute("SELECT card_type, sentence_id, word_id FROM cards ORDER BY id")
    return [(row["card_type"], row["sentence_id"], row["word_id"]) for row in cursor.fetchall()]


# ----- cards -----

def test_ensure_cards_creates_each_card_once_in_list_order(conn, cards):
    cards.ensure_cards([_sentence(1), _word(10), _word(11)])
    cards.ensure_cards([_sentence(1), _word(11), _sentence(2), _word(12), _word(12)])
    assert _rows(conn) == [(SENTENCE_CARD, 1, None), (WORD_CARD, None, 10), (WORD_CARD, None, 11),
                           (SENTENCE_CARD, 2, None), (WORD_CARD, None, 12)]
    assert cards.get(1).state == CardState()
    cards.ensure_cards([])


def test_two_pulls_at_once_create_each_card_once(conn, cards, database_url):
    """Two requests add the same cards at the same moment, as after a cold start on Azure.

    The first request has inserted its cards but not committed yet. The second request must wait
    for it (the sp_getapplock in ensure_cards) and then add nothing. Without the lock, the second
    request reads the cards as missing (CI's test database uses read committed snapshot, as Azure
    SQL does) and its INSERT fails on the unique index once the first commits.
    """
    new = [_sentence(1), _word(10), _word(11)]
    other = db.connect(database_url)
    errors: list[Exception] = []

    def second_request() -> None:
        try:
            MssqlCardRepository(lambda: other).ensure_cards(new)
            other.commit()
        except Exception as error:   # collected, so the assertion below can show it
            errors.append(error)

    try:
        cards.ensure_cards(new)                    # first request: inserted, not committed
        thread = threading.Thread(target=second_request)
        thread.start()
        thread.join(timeout=1)
        assert thread.is_alive()                   # the second request is waiting for the first
        conn.commit()
        thread.join(timeout=15)
    finally:
        other.close()
    assert errors == []
    assert _rows(conn) == [(SENTENCE_CARD, 1, None), (WORD_CARD, None, 10), (WORD_CARD, None, 11)]


def test_one_card_per_word_is_enforced_by_the_filtered_index(conn, cards):
    cards.ensure_cards([_word(10)])
    with pytest.raises(pymssql.IntegrityError):
        conn.cursor().execute("INSERT INTO cards (card_type, word_id) VALUES (N'word', 10)")


def test_a_card_must_point_at_exactly_one_thing(conn):
    with pytest.raises(pymssql.IntegrityError):
        conn.cursor().execute("INSERT INTO cards (card_type, word_id, sentence_id) VALUES (N'word', 1, 2)")


def test_get_unknown_card_returns_none(cards):
    assert cards.get(999) is None


def test_saved_state_is_read_back_with_a_real_date(cards):
    cards.ensure_cards([_sentence(1)])
    state = CardState(ease_factor=2.36, interval_days=6, repetitions=2, due_date=date(2026, 11, 23))
    cards.save_state(1, state)
    assert cards.get(1).state == state


def test_save_states_updates_many_cards_across_batches(cards, monkeypatch):
    monkeypatch.setattr(db, "ROWS_PER_BATCH", 2)
    cards.ensure_cards([_word(w) for w in range(10, 15)])
    states = {card_id: CardState(2.5, 60 + card_id, 2, TODAY + timedelta(days=60 + card_id)) for card_id in range(1, 6)}
    cards.save_states(states)
    assert {card_id: cards.get(card_id).state for card_id in range(1, 6)} == states


def test_next_due_picks_the_oldest_due_card_and_skips_future_and_new(cards):
    cards.ensure_cards([_word(w) for w in (10, 11, 12, 13)])  # ids 1-4
    cards.save_state(1, CardState(due_date=TODAY + timedelta(days=1)))
    cards.save_state(2, CardState(due_date=TODAY))
    cards.save_state(3, CardState(due_date=TODAY - timedelta(days=2)))
    assert cards.next_due(TODAY).id == 3
    assert cards.count_due(TODAY) == 2


def test_next_new_picks_the_lowest_id_and_none_when_empty(cards):
    assert cards.next_new() is None and cards.next_due(TODAY) is None
    cards.ensure_cards([_word(10), _word(11)])
    cards.save_state(1, CardState(due_date=TODAY))
    assert cards.next_new().id == 2
    assert cards.count_all() == 2


def test_max_sentence_id_is_where_the_next_pull_starts(cards):
    assert cards.max_sentence_id() == 0
    cards.ensure_cards([_sentence(3), _word(10), _sentence(7)])
    assert cards.max_sentence_id() == 7


def test_new_cards_for_returns_only_new_cards_of_the_given_content(cards, monkeypatch):
    monkeypatch.setattr(db, "ROWS_PER_BATCH", 1)
    cards.ensure_cards([_sentence(1), _word(10), _word(11), _word(12)])   # ids 1-4
    cards.save_state(3, CardState(interval_days=1, repetitions=1, due_date=TODAY))
    assert [card.id for card in cards.new_cards_for([1], [10, 11])] == [1, 2]
    assert cards.new_cards_for([], []) == []


# ----- reviews -----

def test_count_reviews_on_a_day(cards, review_log):
    cards.ensure_cards([_word(10)])
    review_log.add(_review(1, "2026-11-16T23:59:59"))
    review_log.add(_review(1, "2026-11-17T00:00:00"))
    review_log.add(_review(1, "2026-11-17T21:00:00"))
    assert review_log.count_reviews_on(TODAY) == 2


def test_count_first_reviews_only_counts_cards_first_seen_that_day(cards, review_log):
    cards.ensure_cards([_word(10), _word(11), _word(12)])
    review_log.add(_review(1, "2026-11-16T20:00:00"))  # card 1 first seen yesterday...
    review_log.add(_review(1, "2026-11-17T09:00:00"))  # ...so today's review is not "new"
    review_log.add(_review(2, "2026-11-17T10:00:00"))
    review_log.add(_review(2, "2026-11-17T11:00:00"))
    review_log.add(_review(3, "2026-11-17T12:00:00"))
    assert review_log.count_first_reviews_on(TODAY) == 2


def test_quality_outside_0_to_5_is_rejected_by_the_schema(cards, review_log):
    cards.ensure_cards([_word(10)])
    with pytest.raises(pymssql.IntegrityError):
        review_log.add(Review(1, datetime(2026, 11, 17), 9, 1, 2.5))


# ----- settings -----

def test_settings_store_returns_none_then_the_latest_value(conn):
    settings = MssqlSettingsStore(lambda: conn)
    assert settings.get("new_cards_per_day") is None
    settings.set("new_cards_per_day", "10")
    settings.set("new_cards_per_day", "20")
    settings.set("level_name", "Intermediate")
    assert (settings.get("new_cards_per_day"), settings.get("level_name")) == ("20", "Intermediate")
