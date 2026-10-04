"""Tests for loading the seed files on first start (trainer.content.seed)."""

from datetime import date

import pytest

from trainer import create_app
from trainer.config import BUNDLED_SEED_DIR, Config

ATTRIBUTION = "CC-BY 2.0 (France) Attribution: tatoeba.org #1 (a) & #2 (b)"
TODAY = date(2026, 10, 4)


@pytest.fixture
def seed_dir(tmp_path):
    folder = tmp_path / "seed"
    folder.mkdir()
    (folder / "sentences.tsv").write_text(
        f"El gato come.\tThe cat eats.\t{ATTRIBUTION}\nEl perro come.\tThe dog eats.\t{ATTRIBUTION}\n",
        encoding="utf-8",
    )
    (folder / "words.tsv").write_text("come\t1\ngato\t2\nperro\t3\n", encoding="utf-8")
    return folder


def _start(tmp_path, seed_dir):
    return create_app(Config(data_dir=str(tmp_path / "data"), seed_dir=str(seed_dir)))


def _services(app):
    return app.extensions["content_service"], app.extensions["review_service"]


def test_first_start_imports_the_seed_with_ranks_attribution_and_cards(tmp_path, seed_dir):
    app = _start(tmp_path, seed_dir)
    content, reviews = _services(app)
    with app.app_context():
        assert content.count_sentences() == 2
        assert content.get_sentence(1).sentence.source == ATTRIBUTION
        assert [(w.headword, w.frequency_rank) for w in content.get_sentence(1).words] == [("come", 1), ("gato", 2)]
        assert reviews.stats(TODAY).total_cards == 5  # 2 sentence cards + come, gato, perro


def test_later_starts_do_not_import_again(tmp_path, seed_dir):
    _start(tmp_path, seed_dir)
    app = _start(tmp_path, seed_dir)
    content, _ = _services(app)
    with app.app_context():
        assert content.count_sentences() == 2


def test_missing_seed_files_start_an_empty_app(tmp_path):
    app = _start(tmp_path, tmp_path / "nothing-here")
    content, _ = _services(app)
    with app.app_context():
        assert content.count_sentences() == 0


def test_the_committed_seed_loads_2000_sentences(tmp_path):
    app = _start(tmp_path, BUNDLED_SEED_DIR)
    content, reviews = _services(app)
    with app.app_context():
        assert content.count_sentences() == 2000
        assert reviews.stats(TODAY).total_cards > 2000  # every sentence plus its words
