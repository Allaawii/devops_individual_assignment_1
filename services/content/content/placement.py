"""Placement quiz: find out how much Spanish the learner already knows.

The seed sentences are stored easiest first, so they can be cut into equal bands, one per level.
The quiz asks a few multiple-choice questions from every band except the hardest. The learner's
level is the number of bands, counted from the easiest, where every answer was right.

Pure functions only: no Flask and no database, so the quiz is easy to test.
"""

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from content.models import Sentence
from content.tokenizer import extract_words

LEVELS = ("Starter", "Beginner", "Elementary", "Intermediate", "Advanced")
QUESTIONS_PER_LEVEL = 2
OPTION_COUNT = 4           # the right answer plus 3 wrong ones
DONT_KNOW = "dont-know"    # value of the "I'm not sure" choice; never correct
ENGLISH_WORD = re.compile(r"[a-z']+")


@dataclass(frozen=True)
class Question:
    sentence_id: int
    spanish: str
    answer: str
    options: list[str]     # `answer` plus wrong answers, in shuffled order
    level: int             # the band the sentence comes from (0 = easiest)

    @property
    def field(self) -> str:
        """The form field name that carries the learner's choice."""
        return f"q{self.sentence_id}"


@dataclass(frozen=True)
class _Words:
    """A seed sentence's Spanish content words and English words, worked out once per quiz."""

    spanish: set[str]
    english: set[str]
    length: int        # number of English words

    @classmethod
    def of(cls, sentence: Sentence) -> "_Words":
        english = ENGLISH_WORD.findall(sentence.english_text.lower())
        return cls(set(extract_words(sentence.spanish_text)), set(english), len(english))


def level_bands(seed: Sequence[Sentence]) -> list[Sequence[Sentence]]:
    """Cut the easiest-first seed into len(LEVELS) equal bands (a few leftover hard ones are dropped)."""
    size = len(seed) // len(LEVELS)
    return [seed[i * size:(i + 1) * size] for i in range(len(LEVELS))]


def build_quiz(seed: Sequence[Sentence]) -> list[Question]:
    """QUESTIONS_PER_LEVEL questions from every band but the hardest, easiest first.

    Returns an empty list when the seed is too small to fill the options. The same seed
    always gives the same quiz, so answers can be checked by building it again.
    """
    bands = level_bands(seed)
    if len(bands[0]) < OPTION_COUNT + QUESTIONS_PER_LEVEL:
        return []
    words = {sentence.id: _Words.of(sentence) for sentence in seed}
    return [_question(band[position], level, seed, words)
            for level, band in enumerate(bands[:-1])
            for position in _spread(len(band))]


def score(quiz: Sequence[Question], answers: Mapping[str, str]) -> int:
    """The learner's level: how many bands in a row, from the easiest, were answered fully right."""
    level = 0
    for band in range(len(LEVELS) - 1):
        questions = [q for q in quiz if q.level == band]
        if not questions or any(answers.get(q.field) != q.answer for q in questions):
            break
        level += 1
    return level


def sentences_below(seed: Sequence[Sentence], level: int) -> Sequence[Sentence]:
    """The seed sentences in the bands under `level`: the ones the learner already knows."""
    return [sentence for band in level_bands(seed)[:level] for sentence in band]


def _spread(band_size: int) -> list[int]:
    """Evenly spaced positions inside a band, e.g. a third and two thirds of the way through."""
    return [band_size * (k + 1) // (QUESTIONS_PER_LEVEL + 1) for k in range(QUESTIONS_PER_LEVEL)]


def _question(sentence: Sentence, level: int, seed: Sequence[Sentence],
              words: dict[int, _Words]) -> Question:
    """One question about `sentence`, with the most confusable wrong answers from the seed."""
    rng = random.Random(sentence.id)  # seeded by the id, so the question never changes
    options = _confusable(sentence, seed, words, rng) + [sentence.english_text]
    rng.shuffle(options)
    return Question(sentence.id, sentence.spanish_text, sentence.english_text, options, level)


def _confusable(sentence: Sentence, seed: Sequence[Sentence], words: dict[int, _Words],
                rng: random.Random) -> list[str]:
    """The OPTION_COUNT - 1 English texts that are hardest to tell apart from the right answer.

    A good wrong answer is about as long as the right one (a much longer option gives itself
    away), shares Spanish words with the question (so knowing one word isn't enough) and shares
    English words with the answer (so it looks alike). Sentences whose words are a subset or
    superset of the question's might mean the same thing, so they go last.
    """
    question = words[sentence.id]
    length_slack = max(2, question.length // 2)

    def closeness(other: Sentence) -> tuple[bool, bool, int, int]:
        spanish = words[other.id].spanish
        same_meaning_risk = spanish <= question.spanish or question.spanish <= spanish
        similar_length = abs(words[other.id].length - question.length) <= length_slack
        return (not same_meaning_risk, similar_length, len(spanish & question.spanish),
                len(words[other.id].english & question.english))

    candidates = {other.english_text: other for other in seed}  # one candidate per English text
    candidates.pop(sentence.english_text, None)
    pool = list(candidates.values())
    rng.shuffle(pool)                                  # equally close candidates: a fixed random pick
    pool.sort(key=closeness, reverse=True)             # stable, so the shuffle breaks ties
    return [other.english_text for other in pool[:OPTION_COUNT - 1]]
