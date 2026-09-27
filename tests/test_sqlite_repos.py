"""Tests for the SQLite repositories, each against a fresh temporary database."""

import sqlite3

import pytest

from trainer.content.models import Sentence
from trainer.content.repository import SqliteSentenceRepository, SqliteWordRepository
from trainer.db import connect

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
