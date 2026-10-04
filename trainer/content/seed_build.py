"""Offline tool: turn the Tatoeba Spanish-English export into the committed seed files.

Run once by hand (never at app startup, never with network access):
    python -m trainer.content.seed_build raw/spa-eng.zip --limit 2000

Sentences built from common words come first, so the easiest ones reach the learner first.
"""

import argparse
import csv
import zipfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from trainer.content.tokenizer import WORD_PATTERN, extract_words

MIN_TOKENS = 3
MAX_TOKENS = 12
MAX_PER_RAREST_WORD = 3  # without this cap, 2,000 sentences reuse only ~100 very common words
DEFAULT_LIMIT = 2000
DEFAULT_OUT_DIR = Path(__file__).parent / "seed"


@dataclass(frozen=True)
class Candidate:
    """One parsed line, with its tokens counted once so later steps don't redo the work."""

    english: str
    spanish: str
    attribution: str
    words: tuple[str, ...]  # content words from extract_words
    length: int             # number of tokens, stopwords included


def parse_line(line: str) -> Candidate | None:
    """Parse 'English<TAB>Spanish<TAB>Attribution'. Returns None for a malformed line."""
    parts = [part.strip() for part in line.split("\t")]
    if len(parts) < 3 or not all(parts[:3]):
        return None
    english, spanish, attribution = parts[:3]
    tokens = WORD_PATTERN.findall(spanish.lower())
    return Candidate(english, spanish, attribution, tuple(extract_words(spanish)), len(tokens))


def is_suitable(candidate: Candidate) -> bool:
    """3-12 tokens, no digits, and at least one word that isn't a stopword."""
    return (MIN_TOKENS <= candidate.length <= MAX_TOKENS
            and not any(char.isdigit() for char in candidate.spanish)
            and len(candidate.words) > 0)


def deduplicate(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Keep only the first candidate for each Spanish text."""
    seen: set[str] = set()
    unique = []
    for candidate in candidates:
        if candidate.spanish not in seen:
            seen.add(candidate.spanish)
            unique.append(candidate)
    return unique


def frequency_ranks(candidates: Iterable[Candidate]) -> dict[str, int]:
    """Rank every word by how many sentences use it. Rank 1 is the most common; ties go alphabetically."""
    counts = Counter(word for candidate in candidates for word in candidate.words)
    ordered = sorted(counts, key=lambda word: (-counts[word], word))
    return {word: rank for rank, word in enumerate(ordered, start=1)}


def difficulty(candidate: Candidate, ranks: dict[str, int]) -> tuple[int, int]:
    """The rank of the sentence's rarest word, then its length as the tie-breaker."""
    return max(ranks[word] for word in candidate.words), candidate.length


def select_varied(ordered: Iterable[Candidate], ranks: dict[str, int], limit: int) -> list[Candidate]:
    """Walk the sentences easiest first, keeping at most MAX_PER_RAREST_WORD per rarest word.

    Each word still gets a few example sentences, but the seed keeps moving on to new
    vocabulary instead of filling up with sentences built from the same handful of words.
    """
    chosen: list[Candidate] = []
    uses: Counter[int] = Counter()
    for candidate in ordered:
        rarest_rank = difficulty(candidate, ranks)[0]
        if uses[rarest_rank] < MAX_PER_RAREST_WORD:
            uses[rarest_rank] += 1
            chosen.append(candidate)
            if len(chosen) == limit:
                break
    return chosen


def build_seed(lines: Iterable[str], limit: int) -> tuple[list[Candidate], dict[str, int]]:
    """The whole pipeline: parse, filter, deduplicate, rank, sort easiest first, and pick a varied `limit`.

    Returns the chosen sentences in learning order, and the ranks of the words they use.
    """
    parsed = (parse_line(line) for line in lines)
    candidates = deduplicate(c for c in parsed if c is not None and is_suitable(c))
    ranks = frequency_ranks(candidates)
    ordered = sorted(candidates, key=lambda c: difficulty(c, ranks))
    chosen = select_varied(ordered, ranks, limit)
    used_words = {word for candidate in chosen for word in candidate.words}
    return chosen, {word: rank for word, rank in ranks.items() if word in used_words}


def read_lines(zip_path: Path) -> list[str]:
    """Read the sentence file (spa.txt) out of the downloaded zip."""
    with zipfile.ZipFile(zip_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith("spa.txt"))
        return archive.read(name).decode("utf-8").splitlines()


def write_seed(out_dir: Path, chosen: list[Candidate], ranks: dict[str, int]) -> None:
    """Write sentences.tsv (spanish, english, attribution) and words.tsv (headword, rank)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_tsv(out_dir / "sentences.tsv", ((c.spanish, c.english, c.attribution) for c in chosen))
    _write_tsv(out_dir / "words.tsv", sorted(ranks.items(), key=lambda item: item[1]))


def _write_tsv(path: Path, rows: Iterable[tuple]) -> None:
    """Write tab-separated rows; the csv module quotes any text that needs it."""
    with open(path, "w", encoding="utf-8", newline="") as file:
        csv.writer(file, delimiter="\t", lineterminator="\n").writerows(rows)


def main(argv: list[str] | None = None) -> None:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Build the seed files from the Tatoeba export.")
    parser.add_argument("zip_path", type=Path, help="path to the downloaded spa-eng.zip")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="number of sentences to keep")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    chosen, ranks = build_seed(read_lines(args.zip_path), args.limit)
    write_seed(args.out_dir, chosen, ranks)
    print(f"Wrote {len(chosen)} sentences and {len(ranks)} words to {args.out_dir}")


if __name__ == "__main__":  # pragma: no cover
    main()
