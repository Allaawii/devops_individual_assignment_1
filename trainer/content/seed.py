"""Load the committed seed files into an empty database on first start. No network access."""

import csv
from pathlib import Path

from trainer.content.service import ContentService


def load_seed_if_empty(content: ContentService, seed_dir: Path) -> int:
    """Import seed/sentences.tsv (and the word ranks) if there are no sentences yet.

    Returns how many sentences were added: 0 when the database already has sentences or the
    seed files are missing. The caller commits once afterwards, so the import is one transaction.
    """
    sentences_file, words_file = seed_dir / "sentences.tsv", seed_dir / "words.tsv"
    if content.count_sentences() > 0 or not sentences_file.exists():
        return 0
    ranks = {headword: int(rank) for headword, rank in _read_tsv(words_file)} if words_file.exists() else {}
    return content.import_seed(_read_tsv(sentences_file), ranks)


def _read_tsv(path: Path) -> list[list[str]]:
    with open(path, encoding="utf-8", newline="") as file:
        return list(csv.reader(file, delimiter="\t"))
