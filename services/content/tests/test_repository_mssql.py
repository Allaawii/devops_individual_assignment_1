"""Tests for the SQL Server repositories, each on a freshly migrated database.

Skipped when TEST_DATABASE_URL is not set; CI always sets it.
"""

import pymssql
import pytest

from content import db
from content.models import Sentence
from content.repository import MssqlSentenceRepository, MssqlWordRepository, NewSentence
from content.service import ContentService

CREATED_AT = "2026-11-16T10:00:00"


@pytest.fixture
def sentences(conn) -> MssqlSentenceRepository:
    return MssqlSentenceRepository(lambda: conn)


@pytest.fixture
def words(conn) -> MssqlWordRepository:
    return MssqlWordRepository(lambda: conn)


def _add(repo: MssqlSentenceRepository, spanish: str, english: str = "x", source: str = "user") -> Sentence:
    return repo.add(spanish_text=spanish, english_text=english, grammar_note=None, source=source,
                    created_at=CREATED_AT)


# ----- sentences -----

def test_added_sentence_can_be_read_back_with_accents(sentences):
    added = sentences.add(spanish_text="¿Dónde está el niño?", english_text="Where is the boy?",
                          grammar_note="a note", source="user", created_at=CREATED_AT)
    assert sentences.get(added.id) == added


def test_get_unknown_sentence_returns_none(sentences):
    assert sentences.get(999) is None


def test_exists_matches_exact_text_with_accents_and_case(sentences):
    _add(sentences, "Él sí come")
    assert sentences.exists("Él sí come")
    assert not sentences.exists("él sí come")
    assert not sentences.exists("Él si come")


def test_duplicate_spanish_text_is_rejected_by_the_schema(sentences):
    _add(sentences, "Hola")
    with pytest.raises(pymssql.IntegrityError):
        _add(sentences, "Hola")


def test_count_and_list_page_with_offset(sentences):
    for text in ["Uno", "Dos", "Tres", "Cuatro"]:
        _add(sentences, text)
    assert sentences.count() == 4
    assert [s.spanish_text for s in sentences.list_page(limit=2, offset=1)] == ["Dos", "Tres"]


def test_containing_word_returns_linked_sentences_up_to_limit(sentences, words):
    gato = words.get_or_create("gato")
    for text in ["El gato come", "Un perro", "Mi gato duerme", "Otro gato"]:
        sentence = _add(sentences, text)
        if "gato" in text:
            words.link(sentence.id, gato.id)
    assert [s.spanish_text for s in sentences.containing_word(gato.id, limit=2)] == ["El gato come", "Mi gato duerme"]


def test_seed_skips_sentences_added_by_the_learner(sentences):
    _add(sentences, "Mía")
    seeded = _add(sentences, "Hola", source="tatoeba")
    assert sentences.seed() == [seeded]


def test_add_many_keeps_list_order_in_the_ids(sentences, monkeypatch):
    monkeypatch.setattr(db, "ROWS_PER_BATCH", 2)   # three batches for five rows
    texts = ["Cinco", "Uno", "Tres", "Dos", "Cuatro"]
    sentences.add_many([NewSentence(t, "x", None, "tatoeba", CREATED_AT) for t in texts])
    assert [s.spanish_text for s in sentences.list_page(10, 0)] == texts
    assert sentences.ids_by_text() == {text: position + 1 for position, text in enumerate(texts)}


def test_ids_after_is_ascending_and_limited(sentences):
    for text in ["Uno", "Dos", "Tres", "Cuatro"]:
        _add(sentences, text)
    assert sentences.ids_after(1, 2) == [2, 3]
    assert sentences.ids_after(4, 20) == []


# ----- words -----

def test_get_or_create_inserts_once(words):
    first = words.get_or_create("gato")
    assert words.get_or_create("gato") == first
    assert first.meaning is None and first.frequency_rank is None


def test_headwords_differ_by_accent(words):
    assert words.get_or_create("si").id != words.get_or_create("sí").id


def test_get_unknown_word_returns_none(words):
    assert words.get(999) is None


def test_link_twice_is_harmless_and_for_sentence_lists_words(sentences, words):
    sentence = _add(sentences, "El gato negro")
    gato, negro = words.get_or_create("gato"), words.get_or_create("negro")
    words.link(sentence.id, gato.id)
    words.link(sentence.id, negro.id)
    words.link(sentence.id, gato.id)
    assert words.for_sentence(sentence.id) == [gato, negro]


def test_add_many_link_many_and_grouped_word_ids(sentences, words):
    words.add_many([("casa", 1), ("perro", 2), ("gato", None)])
    first, second = _add(sentences, "Uno"), _add(sentences, "Dos")
    ids = words.ids_by_headword()
    assert ids == {"casa": 1, "perro": 2, "gato": 3}
    words.link_many([(first.id, ids["gato"]), (first.id, ids["casa"]), (second.id, ids["perro"])])
    assert words.word_ids_by_sentence([first.id, second.id]) == {first.id: [1, 3], second.id: [2]}
    assert words.word_ids_by_sentence([]) == {}


def test_ids_in_sentences_lists_each_word_once_across_batches(sentences, words, monkeypatch):
    monkeypatch.setattr(db, "ROWS_PER_BATCH", 1)     # one query per sentence
    gato, perro = words.get_or_create("gato"), words.get_or_create("perro")
    first, second, other = _add(sentences, "Uno"), _add(sentences, "Dos"), _add(sentences, "Tres")
    words.link(first.id, perro.id)
    words.link(second.id, perro.id)
    words.link(second.id, gato.id)
    words.link(other.id, words.get_or_create("casa").id)
    assert words.ids_in_sentences([first.id, second.id]) == [gato.id, perro.id]


def test_set_meaning(words):
    gato = words.get_or_create("gato")
    words.set_meaning(gato.id, "cat")
    assert words.get(gato.id).meaning == "cat"


def test_list_page_puts_empty_meanings_first_then_rank_then_unranked(words):
    words.add_many([("casa", 1), ("perro", 2), ("gato", 3), ("zapato", None)])
    words.set_meaning(words.get_or_create("casa").id, "house")
    assert [w.headword for w in words.list_page(limit=10, offset=0)] == ["perro", "gato", "zapato", "casa"]


# ----- the batched seed import, end to end -----

def test_import_seed_matches_adding_one_by_one(conn):
    service = ContentService(MssqlSentenceRepository(lambda: conn), MssqlWordRepository(lambda: conn))
    rows = [("El gato come.", "The cat eats.", "tatoeba #1"), ("Hay que comer.", "One must eat.", "tatoeba #2")]
    assert service.import_seed(rows, {"come": 1, "gato": 2}) == 2
    first = service.get_sentence(1)
    assert [(w.headword, w.frequency_rank) for w in first.words] == [("come", 1), ("gato", 2)]
    assert service.get_sentence(2).sentence.grammar_note.startswith("Hay que")
    assert [item.id for item in service.feed(0, 20)] == [1, 2]


# ----- transactions -----

def test_repositories_do_not_commit(conn, sentences, database_url):
    _add(sentences, "Hola")
    other = db.connect(database_url)
    try:
        cursor = other.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM sentences WITH (READPAST)")  # skip the uncommitted row
        assert cursor.fetchone()["n"] == 0
    finally:
        other.close()
