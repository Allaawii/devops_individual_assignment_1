"""Tests for the placement quiz (content.placement): pure functions, no database."""

import pytest

from content.models import Sentence
from content.placement import (
    DONT_KNOW,
    LEVELS,
    OPTION_COUNT,
    QUESTIONS_PER_LEVEL,
    build_quiz,
    level_bands,
    score,
    sentences_below,
)

TESTED_LEVELS = len(LEVELS) - 1  # the hardest band is never asked about


def _seed(count: int) -> list[Sentence]:
    """`count` seed sentences, easiest first, each with its own English text."""
    return [Sentence(i, f"frase {i}", f"sentence {i}", None, "tatoeba", "2026-10-04") for i in range(1, count + 1)]


def _answers(quiz, right_bands: int) -> dict[str, str]:
    """Answer the first `right_bands` bands correctly and say "not sure" to the rest."""
    return {q.field: q.answer if q.level < right_bands else DONT_KNOW for q in quiz}


# ----- bands -----

def test_seed_is_cut_into_one_equal_band_per_level():
    bands = level_bands(_seed(52))
    assert len(bands) == len(LEVELS)
    assert all(len(band) == 10 for band in bands)    # 2 leftover sentences are dropped
    assert bands[0][0].id == 1 and bands[1][0].id == 11


def test_sentences_below_a_level_are_the_easiest_bands():
    seed = _seed(50)
    assert sentences_below(seed, 0) == []
    assert [s.id for s in sentences_below(seed, 2)] == list(range(1, 21))


# ----- building the quiz -----

def test_quiz_asks_about_every_band_but_the_hardest():
    quiz = build_quiz(_seed(100))
    assert len(quiz) == QUESTIONS_PER_LEVEL * TESTED_LEVELS
    assert [q.level for q in quiz] == sorted(q.level for q in quiz)
    assert {q.level for q in quiz} == set(range(TESTED_LEVELS))


def test_each_question_has_four_different_options_including_the_answer():
    for question in build_quiz(_seed(100)):
        assert len(set(question.options)) == OPTION_COUNT
        assert question.answer in question.options
        assert question.answer == f"sentence {question.sentence_id}"


def _letters(n: int) -> str:
    """A made-up word for number n (aa, ab, ...); the tokenizer ignores digits, so words need letters."""
    return "".join(chr(ord("a") + d) for d in divmod(n, 26))


def _two_pattern_seed(count: int) -> list[Sentence]:
    """Alternating "Veo X hoy." / "Como X ahora." sentences, so each one has look-alikes."""
    seed = []
    for i in range(1, count + 1):
        word = _letters(i)
        spanish, english = (f"Veo {word} hoy.", f"I see {word} today.") if i % 2 else \
                           (f"Como {word} ahora.", f"I eat {word} now.")
        seed.append(Sentence(i, spanish, english, None, "tatoeba", "2026-10-04"))
    return seed


def test_wrong_options_share_spanish_words_with_the_question():
    for question in build_quiz(_two_pattern_seed(100)):
        pattern = question.answer.split()[1]                 # "see" or "eat"
        assert all(option.split()[1] == pattern for option in question.options)


def test_a_sentence_that_might_mean_the_same_is_not_used_as_a_wrong_option():
    seed = _two_pattern_seed(50)
    question = build_quiz(seed)[0]                           # about sentence 4: "Como ae ahora."
    # Same content words and almost the same English: it would rank first without the subset rule.
    paraphrase = Sentence(50, f"Ahora como {_letters(4)}.", f"Now I eat {_letters(4)}.", None, "tatoeba", "x")
    quiz = build_quiz(seed[:-1] + [paraphrase])
    assert quiz[0].sentence_id == question.sentence_id
    assert paraphrase.english_text not in quiz[0].options


def test_the_same_seed_always_gives_the_same_quiz():
    assert build_quiz(_seed(100)) == build_quiz(_seed(100))


def test_answer_is_not_always_in_the_same_position():
    positions = {q.options.index(q.answer) for q in build_quiz(_seed(100))}
    assert len(positions) > 1


def test_a_much_longer_sentence_is_not_used_as_a_wrong_option():
    seed = _two_pattern_seed(50)
    # Question 2 is "Veo ah hoy." / "I see ah today." This one shares as many Spanish words as the
    # other "Veo X hoy." sentences and more English words, so only its length should rule it out.
    long_one = Sentence(50, "Veo ah mañana.", "I see ah and many other things in a very long sentence today.",
                        None, "tatoeba", "x")
    quiz = build_quiz(seed[:-1] + [long_one])
    assert quiz[1].spanish == "Veo ah hoy."
    assert long_one.english_text not in quiz[1].options


@pytest.mark.parametrize("count", [0, 5, 29])
def test_too_small_a_seed_gives_no_quiz(count):
    assert build_quiz(_seed(count)) == []


def test_question_field_name_uses_the_sentence_id():
    assert build_quiz(_seed(100))[0].field.startswith("q")


# ----- scoring -----

@pytest.mark.parametrize("right_bands", range(TESTED_LEVELS + 1))
def test_level_is_the_number_of_bands_answered_right(right_bands):
    quiz = build_quiz(_seed(100))
    assert score(quiz, _answers(quiz, right_bands)) == right_bands


def test_one_wrong_answer_stops_the_climb_even_if_harder_bands_are_right():
    quiz = build_quiz(_seed(100))
    answers = _answers(quiz, TESTED_LEVELS)
    first_of_band_1 = next(q for q in quiz if q.level == 1)
    answers[first_of_band_1.field] = DONT_KNOW
    assert score(quiz, answers) == 1


def test_no_answers_means_starter():
    assert score(build_quiz(_seed(100)), {}) == 0


def test_empty_quiz_scores_starter():
    assert score([], {}) == 0
