"""ContentService: the single entry point (Facade) into the content domain.

It is also the Observer subject: whenever a sentence is added it calls every
subscribed listener with the new sentence id and its word ids. This is how the
scheduler learns about new content without the content package importing it.
"""

from collections.abc import Callable, Iterable
from datetime import datetime

from trainer.content.grammar_rules import tag_grammar
from trainer.content.models import Page, Sentence, SentenceDetail, T, Word
from trainer.content.repository import SentenceRepository, WordRepository
from trainer.content.tokenizer import extract_words

PAGE_SIZE = 50
EXAMPLE_LIMIT = 3

SentenceAddedListener = Callable[[int, list[int]], None]
SeedRow = tuple[str, str, str]  # (spanish, english, attribution)


class ContentService:
    def __init__(self, sentence_repo: SentenceRepository, word_repo: WordRepository,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self._sentences = sentence_repo
        self._words = word_repo
        self._clock = clock
        self._listeners: list[SentenceAddedListener] = []

    # ----- observer -----

    def subscribe(self, listener: SentenceAddedListener) -> None:
        """Register a function to be called as listener(sentence_id, word_ids) on every new sentence."""
        self._listeners.append(listener)

    def _notify(self, sentence_id: int, word_ids: list[int]) -> None:
        for listener in self._listeners:
            listener(sentence_id, word_ids)

    # ----- writing -----

    def add_sentence(self, spanish: str, english: str, grammar_note: str | None = None,
                     source: str = "user") -> Sentence:
        """Validate and store a sentence, link its words, then notify listeners.

        Raises ValueError if either text is empty or the Spanish text already exists.
        """
        spanish, english = spanish.strip(), english.strip()
        if not spanish or not english:
            raise ValueError("Both the Spanish and the English text are required.")
        if self._sentences.exists(spanish):
            raise ValueError(f"The sentence '{spanish}' already exists.")

        note = _blank_to_none(grammar_note) or tag_grammar(spanish)
        sentence = self._sentences.add(
            spanish_text=spanish, english_text=english, grammar_note=note,
            source=source, created_at=self._clock().isoformat(timespec="seconds"),
        )
        word_ids = [self._words.get_or_create(headword).id for headword in extract_words(spanish)]
        for word_id in word_ids:
            self._words.link(sentence.id, word_id)

        self._notify(sentence.id, word_ids)
        return sentence

    def import_seed(self, rows: Iterable[SeedRow], word_ranks: dict[str, int]) -> int:
        """Store frequency ranks, then add every seed row. Returns how many rows were added.

        The caller commits once at the end, so the whole import is one transaction.
        """
        self._words.set_frequency_ranks(word_ranks)
        added = 0
        for spanish, english, attribution in rows:
            self.add_sentence(spanish, english, source=attribution)
            added += 1
        return added

    def set_meaning(self, word_id: int, meaning: str | None) -> None:
        """Save the learner's meaning for a word; a blank meaning is stored as empty (NULL)."""
        self._words.set_meaning(word_id, _blank_to_none(meaning))

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
