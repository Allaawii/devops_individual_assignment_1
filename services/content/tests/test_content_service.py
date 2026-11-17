"""Tests for ContentService, using in-memory fake repositories."""

import pytest

from content.models import FeedItem
from content.service import FEED_MAX, MAX_NOTE_LENGTH, MAX_TEXT_LENGTH, PAGE_SIZE, ContentService

ATTRIBUTION = "CC-BY 2.0 (France) tatoeba.org #1"


def _headwords(service: ContentService, sentence_id: int) -> list[str]:
    return [word.headword for word in service.get_sentence(sentence_id).words]


# ----- add_sentence -----

def test_add_sentence_strips_text_and_sets_defaults(service):
    sentence = service.add_sentence("  El gato come.  ", " The cat eats. ")
    assert sentence.spanish_text == "El gato come."
    assert sentence.english_text == "The cat eats."
    assert sentence.source == "user"
    assert sentence.created_at == "2026-11-16T10:30:00"


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


@pytest.mark.parametrize("spanish, english, note", [
    ("a" * (MAX_TEXT_LENGTH + 1), "x", None),
    ("Hola", "x" * (MAX_TEXT_LENGTH + 1), None),
    ("Hola", "Hello", "n" * (MAX_NOTE_LENGTH + 1)),
])
def test_text_longer_than_its_column_is_rejected(service, sentence_repo, spanish, english, note):
    with pytest.raises(ValueError):
        service.add_sentence(spanish, english, note)
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


# ----- import_seed -----

def test_import_seed_stores_ranked_words_first_then_sentences_and_links(service, word_repo):
    rows = [("El gato come.", "The cat eats.", ATTRIBUTION), ("Hay que comer.", "One must eat.", ATTRIBUTION)]
    added = service.import_seed(rows, {"come": 1, "perro": 2})
    assert added == 2
    assert [(w.headword, w.frequency_rank) for w in word_repo.rows.values()] == [
        ("come", 1), ("perro", 2), ("gato", None), ("hay", None), ("comer", None),
    ]
    first, second = service.get_sentence(1), service.get_sentence(2)
    assert first.sentence.source == ATTRIBUTION and first.sentence.created_at == "2026-11-16T10:30:00"
    assert [w.headword for w in first.words] == ["come", "gato"]
    assert second.sentence.grammar_note.startswith("Hay que")


def test_import_seed_skips_empty_and_repeated_rows(service):
    rows = [("Hola", "Hello", "t"), ("  ", "Blank", "t"), ("Hola", "Hi again", "t"), ("Adiós", "Bye", "t")]
    assert service.import_seed(rows, {}) == 2
    assert [s.spanish_text for s in service.list_sentences(1).items] == ["Hola", "Adiós"]


def test_import_seed_reuses_words_that_already_exist(service, word_repo):
    gato = word_repo.get_or_create("gato")
    service.import_seed([("El gato come.", "The cat eats.", "t")], {"gato": 1})
    assert word_repo.ids_by_headword()["gato"] == gato.id
    assert len(word_repo.rows) == 2


# ----- words -----

def test_set_meaning_strips_text_and_returns_the_word(service, word_repo):
    word = word_repo.get_or_create("gato")
    assert service.set_meaning(word.id, "  cat ").meaning == "cat"
    assert service.get_word(word.id).meaning == "cat"


def test_blank_meaning_is_stored_as_none(service, word_repo):
    word = word_repo.get_or_create("gato")
    service.set_meaning(word.id, "cat")
    assert service.set_meaning(word.id, "   ").meaning is None


def test_meaning_of_unknown_word_returns_none(service):
    assert service.set_meaning(999, "cat") is None


def test_too_long_meaning_is_rejected(service, word_repo):
    word = word_repo.get_or_create("gato")
    with pytest.raises(ValueError):
        service.set_meaning(word.id, "x" * (MAX_TEXT_LENGTH + 1))
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


# ----- feed (the scheduler's pull) -----

def test_feed_returns_the_sentences_after_an_id_with_their_words(service, word_repo):
    service.add_sentence("El gato come.", "The cat eats.")      # 1: gato, come
    service.add_sentence("Mi perro come.", "My dog eats.")      # 2: perro, come
    service.add_sentence("Hola", "Hello")                       # 3: hola
    ids = word_repo.ids_by_headword()
    assert service.feed(after_id=1, limit=20) == [
        FeedItem(2, sorted([ids["perro"], ids["come"]])), FeedItem(3, [ids["hola"]]),
    ]


def test_feed_respects_the_limit_and_ends_empty(service):
    _add_many(service, 5)
    assert [item.id for item in service.feed(0, 2)] == [1, 2]
    assert service.feed(5, 20) == []


def test_feed_limit_is_kept_between_1_and_the_maximum(service):
    _add_many(service, FEED_MAX + 5)
    assert len(service.feed(0, 0)) == 1
    assert len(service.feed(0, 10_000)) == FEED_MAX


def test_feed_item_of_a_sentence_without_words_has_no_word_ids(service):
    service.add_sentence("¡Sí!", "Yes!")   # "sí" is a stopword, so the sentence has no words
    assert service.feed(0, 20) == [FeedItem(1, [])]


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


def test_score_placement_returns_level_name_and_known_material(service, word_repo):
    _import_seed(service, 50)                      # bands of 10 sentences
    quiz = service.placement_quiz()
    result = service.score_placement({q.field: q.answer for q in quiz if q.level == 0})
    assert (result.level, result.level_name) == (1, "Beginner")
    assert result.sentence_ids == list(range(1, 11))
    assert {word_repo.get(w).headword for w in result.word_ids} == {"frase", "número"}  # digits are not words


def test_all_answers_right_gives_the_highest_tested_level(service):
    _import_seed(service, 50)
    result = service.score_placement({q.field: q.answer for q in service.placement_quiz()})
    assert (result.level, result.level_name, len(result.sentence_ids)) == (4, "Advanced", 40)


def test_no_right_answers_means_starter_with_nothing_to_skip(service):
    _import_seed(service, 50)
    result = service.score_placement({})
    assert (result.level, result.level_name, result.sentence_ids, result.word_ids) == (0, "Starter", [], [])


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
