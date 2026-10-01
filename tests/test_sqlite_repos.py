"""Tests for the SQLite repositories, each against a fresh temporary database."""

import sqlite3
from datetime import date, datetime

import pytest

from trainer.content.models import Sentence
from trainer.content.repository import SqliteSentenceRepository, SqliteWordRepository
from trainer.db import connect
from trainer.scheduler.models import SENTENCE_CARD, WORD_CARD, CardState, Review
from trainer.scheduler.repository import SqliteCardRepository, SqliteReviewLog

CREATED_AT = "2026-09-27T10:00:00"


@pytest.fixture
def sentences(conn) -> SqliteSentenceRepository:
    return SqliteSentenceRepository(lambda: conn)


@pytest.fixture
def words(conn) -> SqliteWordRepository:
    return SqliteWordRepository(lambda: conn)


def _add(repo: SqliteSentenceRepository, spanish: str, english: str = "x") -> Sentence:
    return repo.add(spanish_text=spanish, english_text=english, grammar_note=None,
                    source="user", created_at=CREATED_AT)


# ----- SqliteSentenceRepository -----

def test_added_sentence_can_be_read_back(sentences):
    added = sentences.add(spanish_text="Hola", english_text="Hello", grammar_note="a note",
                          source="user", created_at=CREATED_AT)
    assert sentences.get(added.id) == added


def test_get_unknown_sentence_returns_none(sentences):
    assert sentences.get(999) is None


def test_exists_matches_exact_spanish_text(sentences):
    _add(sentences, "Hola")
    assert sentences.exists("Hola")
    assert not sentences.exists("Adiós")


def test_duplicate_spanish_text_is_rejected_by_the_schema(sentences):
    _add(sentences, "Hola")
    with pytest.raises(sqlite3.IntegrityError):
        _add(sentences, "Hola")


def test_count(sentences):
    _add(sentences, "Uno")
    _add(sentences, "Dos")
    assert sentences.count() == 2


def test_list_page_uses_id_order_limit_and_offset(sentences):
    for text in ["Uno", "Dos", "Tres", "Cuatro"]:
        _add(sentences, text)
    page = sentences.list_page(limit=2, offset=1)
    assert [s.spanish_text for s in page] == ["Dos", "Tres"]


def test_containing_word_returns_linked_sentences_up_to_limit(sentences, words):
    gato = words.get_or_create("gato")
    for text in ["El gato come", "Un perro", "Mi gato duerme", "Otro gato"]:
        sentence = _add(sentences, text)
        if "gato" in text:
            words.link(sentence.id, gato.id)
    found = sentences.containing_word(gato.id, limit=2)
    assert [s.spanish_text for s in found] == ["El gato come", "Mi gato duerme"]


# ----- SqliteWordRepository -----

def test_get_or_create_inserts_once(words):
    first = words.get_or_create("gato")
    second = words.get_or_create("gato")
    assert first == second
    assert first.meaning is None and first.frequency_rank is None


def test_get_unknown_word_returns_none(words):
    assert words.get(999) is None


def test_link_twice_is_harmless_and_for_sentence_lists_words(sentences, words):
    sentence = _add(sentences, "El gato negro")
    gato, negro = words.get_or_create("gato"), words.get_or_create("negro")
    words.link(sentence.id, gato.id)
    words.link(sentence.id, negro.id)
    words.link(sentence.id, gato.id)
    assert words.for_sentence(sentence.id) == [gato, negro]


def test_set_meaning(words):
    gato = words.get_or_create("gato")
    words.set_meaning(gato.id, "cat")
    assert words.get(gato.id).meaning == "cat"


def test_set_frequency_ranks_creates_new_and_updates_existing_words(words):
    existing = words.get_or_create("gato")
    words.set_frequency_ranks({"gato": 5, "perro": 2})
    assert words.get(existing.id).frequency_rank == 5
    assert words.get_or_create("perro").frequency_rank == 2


def test_list_page_puts_empty_meanings_first_then_rank_then_unranked(words):
    words.set_frequency_ranks({"casa": 1, "perro": 2, "gato": 3})
    words.get_or_create("zapato")                                  # no rank
    words.set_meaning(words.get_or_create("casa").id, "house")    # has a meaning
    order = [w.headword for w in words.list_page(limit=10, offset=0)]
    assert order == ["perro", "gato", "zapato", "casa"]


# ----- transactions -----

def test_repositories_do_not_commit(conn, sentences):
    _add(sentences, "Hola")
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    other = connect(db_file)
    try:
        assert other.execute("SELECT COUNT(*) FROM sentences").fetchone()[0] == 0
    finally:
        other.close()


# ----- SqliteCardRepository -----

TODAY = date(2026, 9, 30)


@pytest.fixture
def cards(conn) -> SqliteCardRepository:
    return SqliteCardRepository(lambda: conn)


@pytest.fixture
def review_log(conn) -> SqliteReviewLog:
    return SqliteReviewLog(lambda: conn)


def _review(card_id: int, when: str) -> Review:
    return Review(card_id, datetime.fromisoformat(when), 4, 1, 2.5)


def test_ensure_cards_creates_new_cards_once(conn, cards):
    cards.ensure_sentence_card(1)
    cards.ensure_sentence_card(1)
    cards.ensure_word_cards([10, 11])
    cards.ensure_word_cards([11, 12])
    rows = conn.execute("SELECT card_type, sentence_id, word_id FROM cards ORDER BY id").fetchall()
    assert [tuple(row) for row in rows] == [
        (SENTENCE_CARD, 1, None), (WORD_CARD, None, 10), (WORD_CARD, None, 11), (WORD_CARD, None, 12),
    ]
    assert cards.get(1).state == CardState()


def test_get_unknown_card_returns_none(cards):
    assert cards.get(999) is None


def test_saved_state_is_read_back_with_a_real_date(cards):
    cards.ensure_sentence_card(1)
    state = CardState(ease_factor=2.36, interval_days=6, repetitions=2, due_date=date(2026, 10, 6))
    cards.save_state(1, state)
    assert cards.get(1).state == state


def test_next_due_picks_the_oldest_due_card_and_skips_future_and_new(cards):
    cards.ensure_word_cards([10, 11, 12, 13])  # ids 1-4
    cards.save_state(1, CardState(due_date=date(2026, 10, 1)))  # future
    cards.save_state(2, CardState(due_date=date(2026, 9, 30)))
    cards.save_state(3, CardState(due_date=date(2026, 9, 28)))  # oldest
    # card 4 is new
    assert cards.next_due(TODAY).id == 3
    assert cards.count_due(TODAY) == 2


def test_next_new_picks_the_lowest_id(cards):
    cards.ensure_word_cards([10, 11])
    cards.save_state(1, CardState(due_date=TODAY))
    assert cards.next_new().id == 2
    assert cards.count_new() == 1


def test_no_due_or_new_cards_returns_none(cards):
    assert cards.next_due(TODAY) is None
    assert cards.next_new() is None


# ----- SqliteReviewLog -----

def test_count_reviews_on_a_day(cards, review_log):
    cards.ensure_word_cards([10])
    review_log.add(_review(1, "2026-09-29T20:00:00"))
    review_log.add(_review(1, "2026-09-30T09:00:00"))
    review_log.add(_review(1, "2026-09-30T21:00:00"))
    assert review_log.count_reviews_on(TODAY) == 2


def test_count_first_reviews_only_counts_cards_first_seen_that_day(cards, review_log):
    cards.ensure_word_cards([10, 11, 12])
    review_log.add(_review(1, "2026-09-29T20:00:00"))  # card 1 first seen yesterday...
    review_log.add(_review(1, "2026-09-30T09:00:00"))  # ...so today's review is not "new"
    review_log.add(_review(2, "2026-09-30T10:00:00"))  # card 2 first seen today
    review_log.add(_review(2, "2026-09-30T11:00:00"))
    review_log.add(_review(3, "2026-09-30T12:00:00"))  # card 3 first seen today
    assert review_log.count_first_reviews_on(TODAY) == 2
