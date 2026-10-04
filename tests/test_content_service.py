"""Tests for ContentService, using in-memory fake repositories."""

from datetime import datetime

import pytest

from tests.fakes import FakeSentenceRepository, FakeWordRepository
from trainer.content.service import PAGE_SIZE, ContentService

FIXED_NOW = datetime(2026, 9, 28, 10, 30, 0)


@pytest.fixture
def sentence_repo() -> FakeSentenceRepository:
    return FakeSentenceRepository()


@pytest.fixture
def word_repo(sentence_repo) -> FakeWordRepository:
    return FakeWordRepository(sentence_repo.links)


@pytest.fixture
def service(sentence_repo, word_repo) -> ContentService:
    return ContentService(sentence_repo, word_repo, clock=lambda: FIXED_NOW)


@pytest.fixture
def calls(service) -> list[tuple[int, list[int]]]:
    """Every notification the service sends, recorded in order."""
    received: list[tuple[int, list[int]]] = []
    service.subscribe(lambda sentence_id, word_ids: received.append((sentence_id, word_ids)))
    return received


def _headwords(service: ContentService, sentence_id: int) -> list[str]:
    return [word.headword for word in service.get_sentence(sentence_id).words]


# ----- add_sentence -----

def test_add_sentence_strips_text_and_sets_defaults(service):
    sentence = service.add_sentence("  El gato come.  ", " The cat eats. ")
    assert sentence.spanish_text == "El gato come."
    assert sentence.english_text == "The cat eats."
    assert sentence.source == "user"
    assert sentence.created_at == "2026-09-28T10:30:00"


def test_add_sentence_links_its_words(service):
    sentence = service.add_sentence("El gato come.", "The cat eats.")
    assert _headwords(service, sentence.id) == ["gato", "come"]


def test_word_is_reused_across_sentences(service, word_repo):
    first = service.add_sentence("El gato come.", "The cat eats.")
    second = service.add_sentence("Mi gato duerme.", "My cat sleeps.")
    gato = word_repo.get_or_create("gato")
    assert len(word_repo.rows) == 3  # gato, come, duerme
    assert service.example_sentences(gato.id) == [first, second]


@pytest.mark.parametrize("spanish, english", [("", "Hello"), ("Hola", ""), ("   ", "Hello")])
def test_empty_text_is_rejected(service, sentence_repo, spanish, english):
    with pytest.raises(ValueError):
        service.add_sentence(spanish, english)
    assert sentence_repo.count() == 0


def test_duplicate_sentence_is_rejected_even_with_extra_spaces(service):
    service.add_sentence("Hola", "Hello")
    with pytest.raises(ValueError):
        service.add_sentence("  Hola ", "Hi")


def test_grammar_note_is_added_automatically_when_missing(service):
    sentence = service.add_sentence("Hay que estudiar.", "One must study.")
    assert sentence.grammar_note.startswith("Hay que")


def test_given_grammar_note_is_kept(service):
    sentence = service.add_sentence("Hay que estudiar.", "One must study.", grammar_note="My note")
    assert sentence.grammar_note == "My note"


def test_blank_grammar_note_falls_back_to_automatic(service):
    sentence = service.add_sentence("Hay que estudiar.", "One must study.", grammar_note="   ")
    assert sentence.grammar_note.startswith("Hay que")


def test_sentence_without_matching_rule_has_no_note(service):
    assert service.add_sentence("El gato come.", "The cat eats.").grammar_note is None


# ----- observer -----

def test_listener_receives_sentence_id_and_word_ids(service, word_repo, calls):
    sentence = service.add_sentence("El gato come.", "The cat eats.")
    gato, come = word_repo.get_or_create("gato"), word_repo.get_or_create("come")
    assert calls == [(sentence.id, [gato.id, come.id])]


def test_every_listener_is_notified(service, calls):
    second: list[int] = []
    service.subscribe(lambda sentence_id, word_ids: second.append(sentence_id))
    sentence = service.add_sentence("Hola", "Hello")
    assert len(calls) == 1
    assert second == [sentence.id]


def test_listener_is_not_called_when_sentence_is_rejected(service, calls):
    with pytest.raises(ValueError):
        service.add_sentence("", "Hello")
    assert calls == []


# ----- import_seed -----

def test_import_seed_sets_ranks_and_keeps_attribution(service, word_repo, calls):
    rows = [("El gato come.", "The cat eats.", "CC-BY 2.0 (France) tatoeba.org #1")]
    added = service.import_seed(rows, {"gato": 1, "come": 2})
    assert added == 1
    assert service.get_sentence(1).sentence.source == "CC-BY 2.0 (France) tatoeba.org #1"
    assert word_repo.get_or_create("gato").frequency_rank == 1
    assert len(calls) == 1  # seeded sentences still create cards via the observer


# ----- words -----

def test_set_meaning_strips_text(service, word_repo):
    word = word_repo.get_or_create("gato")
    service.set_meaning(word.id, "  cat ")
    assert service.get_word(word.id).meaning == "cat"


def test_blank_meaning_is_stored_as_none(service, word_repo):
    word = word_repo.get_or_create("gato")
    service.set_meaning(word.id, "cat")
    service.set_meaning(word.id, "   ")
    assert service.get_word(word.id).meaning is None


def test_example_sentences_are_limited_to_three(service, word_repo):
    for text in ["Un gato.", "Otro gato.", "Mi gato.", "Tu gato.", "Su gato."]:
        service.add_sentence(text, "x")
    gato = word_repo.get_or_create("gato")
    assert len(service.example_sentences(gato.id)) == 3


def test_list_words_returns_a_page(service):
    service.add_sentence("El gato come.", "The cat eats.")
    page = service.list_words(page=1)
    assert [w.headword for w in page.items] == ["gato", "come"]
    assert not page.has_next


# ----- reading -----

def test_get_unknown_sentence_returns_none(service):
    assert service.get_sentence(999) is None


def _add_many(service: ContentService, count: int) -> None:
    for i in range(count):
        service.add_sentence(f"Frase {i}", f"Sentence {i}")


def test_sentences_are_paged(service):
    _add_many(service, PAGE_SIZE + 1)
    first, second = service.list_sentences(page=1), service.list_sentences(page=2)
    assert service.count_sentences() == PAGE_SIZE + 1
    assert (len(first.items), first.number, first.has_next) == (PAGE_SIZE, 1, True)
    assert (len(second.items), second.number, second.has_next) == (1, 2, False)


def test_exactly_one_full_page_has_no_next_page(service):
    _add_many(service, PAGE_SIZE)
    assert not service.list_sentences(page=1).has_next


def test_page_below_1_counts_as_page_1(service):
    _add_many(service, 2)
    assert service.list_sentences(page=0) == service.list_sentences(page=1)


# ----- placement quiz -----

def _import_seed(service: ContentService, count: int) -> None:
    rows = [(f"Frase número {i}.", f"Sentence {i}.", "tatoeba") for i in range(1, count + 1)]
    service.import_seed(rows, {})


def test_quiz_is_built_from_seed_sentences_only(service):
    _import_seed(service, 50)
    service.add_sentence("Mi propia frase.", "My own sentence.")
    quiz = service.placement_quiz()
    assert len(quiz) == 8
    assert all(q.sentence_id <= 50 for q in quiz)


def test_no_seed_means_no_quiz(service):
    service.add_sentence("Mi propia frase.", "My own sentence.")
    assert service.placement_quiz() == []


def test_placement_level_checks_the_submitted_answers(service):
    _import_seed(service, 50)
    quiz = service.placement_quiz()
    first_band_right = {q.field: q.answer for q in quiz if q.level == 0}
    assert service.placement_level(first_band_right) == 1
    assert service.placement_level({q.field: q.answer for q in quiz}) == 4


def test_known_material_is_the_easiest_bands_with_their_words(service, word_repo):
    _import_seed(service, 50)                      # bands of 10 sentences
    sentence_ids, word_ids = service.known_material(1)
    assert sentence_ids == list(range(1, 11))
    numbers = {word_repo.get(word_id).headword for word_id in word_ids}
    assert {"frase", "número", "uno"} - numbers == {"uno"}   # number digits are not words
    assert service.known_material(0) == ([], [])

# ----- key words -----

def test_key_words_are_the_rarest_words_first(service):
    service.import_seed([("El perro come pan aquí.", "The dog eats bread here.", "tatoeba")],
                        {"aquí": 1, "come": 2, "perro": 3, "pan": 4})
    detail = service.get_sentence(1)
    assert [w.headword for w in detail.key_words()] == ["pan", "perro", "come"]
    assert [w.headword for w in detail.key_words(limit=1)] == ["pan"]


def test_unranked_words_count_as_rarest_and_keep_sentence_order(service):
    service.import_seed([], {"come": 1})
    service.add_sentence("El gato come pescado.", "The cat eats fish.")
    assert [w.headword for w in service.get_sentence(1).key_words()] == ["gato", "pescado", "come"]