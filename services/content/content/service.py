"""ContentService: the single entry point (Facade) into the content domain.

The API routes call it; it never knows about HTTP. In Assignment 1 it also told the scheduler
about new sentences (Observer). Now the scheduler pulls them through feed() instead (ADR-6).
"""

from collections.abc import Callable, Iterable, Mapping
from datetime import datetime

from content.grammar_rules import tag_grammar
from content.models import USER_SOURCE, FeedItem, Page, PlacementResult, Sentence, SentenceDetail, T, Word
from content.placement import LEVELS, Question, build_quiz, score, sentences_below
from content.repository import NewSentence, SentenceRepository, WordRepository
from content.tokenizer import extract_words

PAGE_SIZE = 50
EXAMPLE_LIMIT = 3
FEED_MAX = 100          # most sentences one pull may ask for
MAX_TEXT_LENGTH = 500   # Spanish, English and meaning columns are NVARCHAR(500)
MAX_NOTE_LENGTH = 1000  # grammar_note is NVARCHAR(1000)

SeedRow = tuple[str, str, str]  # (spanish, english, attribution)


class ContentService:
    def __init__(self, sentence_repo: SentenceRepository, word_repo: WordRepository,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self._sentences = sentence_repo
        self._words = word_repo
        self._clock = clock

    # ----- writing -----

    def add_sentence(self, spanish: str, english: str, grammar_note: str | None = None,
                     source: str = USER_SOURCE) -> Sentence:
        """Validate and store a sentence, then link its words.

        Raises ValueError if a text is empty or too long, or the Spanish text already exists.
        """
        spanish, english, note = spanish.strip(), english.strip(), _blank_to_none(grammar_note)
        if not spanish or not english:
            raise ValueError("Both the Spanish and the English text are required.")
        if len(spanish) > MAX_TEXT_LENGTH or len(english) > MAX_TEXT_LENGTH:
            raise ValueError(f"Each text can be at most {MAX_TEXT_LENGTH} characters.")
        if note and len(note) > MAX_NOTE_LENGTH:
            raise ValueError(f"The grammar note can be at most {MAX_NOTE_LENGTH} characters.")
        if self._sentences.exists(spanish):
            raise ValueError(f"The sentence '{spanish}' already exists.")

        sentence = self._sentences.add(
            spanish_text=spanish, english_text=english, grammar_note=note or tag_grammar(spanish),
            source=source, created_at=self._now(),
        )
        for headword in extract_words(spanish):
            self._words.link(sentence.id, self._words.get_or_create(headword).id)
        return sentence

    def import_seed(self, rows: Iterable[SeedRow], word_ranks: dict[str, int]) -> int:
        """Store the seed on an empty database with a few batched INSERTs. Returns how many sentences were added.

        Adding 3,000 sentences one by one would take thousands of round trips to Azure SQL, so the
        work is done in Python first and then sent in batches: words (ranked ones first, in rank
        order), sentences (in file order, so id order stays easiest first), then the links.
        Rows with an empty text or a Spanish text seen before are skipped. The caller commits once.
        """
        created_at = self._now()
        sentences: dict[str, NewSentence] = {}
        for spanish, english, attribution in rows:
            spanish, english = spanish.strip(), english.strip()
            if spanish and english and spanish not in sentences:
                sentences[spanish] = NewSentence(spanish, english, tag_grammar(spanish), attribution, created_at)
        words_of = {spanish: extract_words(spanish) for spanish in sentences}

        headwords = dict.fromkeys([*word_ranks, *(word for words in words_of.values() for word in words)])
        existing = self._words.ids_by_headword()
        self._words.add_many([(word, word_ranks.get(word)) for word in headwords if word not in existing])
        self._sentences.add_many(list(sentences.values()))

        word_ids, sentence_ids = self._words.ids_by_headword(), self._sentences.ids_by_text()
        self._words.link_many([(sentence_ids[spanish], word_ids[word])
                               for spanish, words in words_of.items() for word in words])
        return len(sentences)

    def set_meaning(self, word_id: int, meaning: str | None) -> Word | None:
        """Save the learner's meaning for a word (blank is stored as NULL). None if the word is unknown.

        Raises ValueError if the meaning is too long.
        """
        if self._words.get(word_id) is None:
            return None
        meaning = _blank_to_none(meaning)
        if meaning and len(meaning) > MAX_TEXT_LENGTH:
            raise ValueError(f"A meaning can be at most {MAX_TEXT_LENGTH} characters.")
        self._words.set_meaning(word_id, meaning)
        return self._words.get(word_id)

    # ----- reading -----

    def count_sentences(self) -> int:
        return self._sentences.count()

    def list_sentences(self, page: int) -> Page[Sentence]:
        """One page of sentences in the order they were added."""
        return _paginate(self._sentences.list_page, page)

    def get_sentence(self, sentence_id: int) -> SentenceDetail | None:
        """The sentence with its words, or None if the id is unknown."""
        sentence = self._sentences.get(sentence_id)
        if sentence is None:
            return None
        return SentenceDetail(sentence, self._words.for_sentence(sentence_id))

    def get_word(self, word_id: int) -> Word | None:
        return self._words.get(word_id)

    def example_sentences(self, word_id: int, limit: int = EXAMPLE_LIMIT) -> list[Sentence]:
        """Up to `limit` sentences that contain the word, shown on the back of a word card."""
        return self._sentences.containing_word(word_id, limit)

    def list_words(self, page: int) -> Page[Word]:
        """One page of words: those still missing a meaning first, then by frequency rank."""
        return _paginate(self._words.list_page, page)

    def feed(self, after_id: int, limit: int) -> list[FeedItem]:
        """The pull: the next sentences after `after_id` (id order) with their word ids.

        The scheduler asks for this when it runs out of new cards. `limit` is kept between 1 and FEED_MAX.
        """
        ids = self._sentences.ids_after(after_id, min(max(limit, 1), FEED_MAX))
        word_ids = self._words.word_ids_by_sentence(ids)
        return [FeedItem(sentence_id, word_ids.get(sentence_id, [])) for sentence_id in ids]

    # ----- placement quiz -----

    def placement_quiz(self) -> list[Question]:
        """The level quiz built from the seed; empty if there aren't enough seed sentences."""
        return build_quiz(self._sentences.seed())

    def score_placement(self, answers: Mapping[str, str]) -> PlacementResult:
        """Check the quiz answers; return the level and the seed sentences and words below it."""
        seed = self._sentences.seed()
        level = score(build_quiz(seed), answers)
        sentence_ids = [sentence.id for sentence in sentences_below(seed, level)]
        return PlacementResult(level, LEVELS[level], sentence_ids, self._words.ids_in_sentences(sentence_ids))

    def _now(self) -> str:
        return self._clock().isoformat(timespec="seconds")


def _blank_to_none(text: str | None) -> str | None:
    """Strip text and turn an empty result into None."""
    if text is None:
        return None
    return text.strip() or None


def _paginate(fetch: Callable[[int, int], list[T]], page: int) -> Page[T]:
    """Fetch one PAGE_SIZE page (pages below 1 count as page 1).

    `fetch(limit, offset)` is a repository's list_page. One extra row is requested so we
    know for certain whether a next page exists.
    """
    number = max(page, 1)
    rows = fetch(PAGE_SIZE + 1, (number - 1) * PAGE_SIZE)
    return Page(rows[:PAGE_SIZE], number, len(rows) > PAGE_SIZE)
