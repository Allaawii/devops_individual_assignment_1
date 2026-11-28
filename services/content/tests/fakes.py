"""In-memory stand-ins for the repositories, so service and API tests need no database."""

from dataclasses import replace

from content.models import USER_SOURCE, Sentence, Word
from content.repository import NewSentence, SentenceRepository, WordRepository


class FakeSentenceRepository(SentenceRepository):
    def __init__(self) -> None:
        self.rows: dict[int, Sentence] = {}
        self.links: set[tuple[int, int]] = set()  # (sentence_id, word_id), shared with FakeWordRepository

    def add(self, *, spanish_text, english_text, grammar_note, source, created_at) -> Sentence:
        sentence = Sentence(len(self.rows) + 1, spanish_text, english_text, grammar_note, source, created_at)
        self.rows[sentence.id] = sentence
        return sentence

    def add_many(self, sentences: list[NewSentence]) -> None:
        for new in sentences:
            fields = new._asdict()
            level = fields.pop("level")
            added = self.add(**fields)
            self.rows[added.id] = replace(added, level=level)

    def exists(self, spanish_text: str) -> bool:
        return any(s.spanish_text == spanish_text for s in self.rows.values())

    def get(self, sentence_id: int) -> Sentence | None:
        return self.rows.get(sentence_id)

    def count(self) -> int:
        return len(self.rows)

    def list_page(self, limit: int, offset: int) -> list[Sentence]:
        return self._in_order()[offset:offset + limit]

    def containing_word(self, word_id: int, limit: int) -> list[Sentence]:
        ids = sorted(s_id for s_id, w_id in self.links if w_id == word_id)
        return [self.rows[s_id] for s_id in ids[:limit]]

    def seed(self) -> list[Sentence]:
        return [s for s in self._in_order() if s.source != USER_SOURCE]

    def ids_after(self, after_id: int, limit: int) -> list[int]:
        return [s.id for s in self._in_order() if s.id > after_id][:limit]

    def ids_by_text(self) -> dict[str, int]:
        return {s.spanish_text: s.id for s in self.rows.values()}

    def _in_order(self) -> list[Sentence]:
        return sorted(self.rows.values(), key=lambda s: s.id)


class FakeWordRepository(WordRepository):
    def __init__(self, links: set[tuple[int, int]]) -> None:
        self.rows: dict[int, Word] = {}
        self.links = links

    def get_or_create(self, headword: str) -> Word:
        for word in self.rows.values():
            if word.headword == headword:
                return word
        return self._add(headword, None)

    def add_many(self, words: list[tuple[str, int | None]]) -> None:
        for headword, rank in words:
            self._add(headword, rank)

    def get(self, word_id: int) -> Word | None:
        return self.rows.get(word_id)

    def ids_by_headword(self) -> dict[str, int]:
        return {w.headword: w.id for w in self.rows.values()}

    def link(self, sentence_id: int, word_id: int) -> None:
        self.links.add((sentence_id, word_id))

    def link_many(self, links: list[tuple[int, int]]) -> None:
        self.links.update(links)

    def for_sentence(self, sentence_id: int) -> list[Word]:
        return [self.rows[w_id] for s_id, w_id in sorted(self.links) if s_id == sentence_id]

    def word_ids_by_sentence(self, sentence_ids: list[int]) -> dict[int, list[int]]:
        grouped: dict[int, list[int]] = {}
        for s_id, w_id in sorted(self.links):
            if s_id in sentence_ids:
                grouped.setdefault(s_id, []).append(w_id)
        return grouped

    def ids_in_sentences(self, sentence_ids: list[int]) -> list[int]:
        wanted = set(sentence_ids)
        return sorted({w_id for s_id, w_id in self.links if s_id in wanted})

    def list_page(self, limit: int, offset: int) -> list[Word]:
        return sorted(self.rows.values(), key=lambda w: w.id)[offset:offset + limit]

    def set_meaning(self, word_id: int, meaning: str | None) -> None:
        self.rows[word_id] = replace(self.rows[word_id], meaning=meaning)

    def _add(self, headword: str, rank: int | None) -> Word:
        word = Word(len(self.rows) + 1, headword, None, rank)
        self.rows[word.id] = word
        return word
