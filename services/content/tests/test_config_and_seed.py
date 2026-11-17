"""Tests for reading the environment (content.config) and the first-start seed loader (content.seed)."""

import pytest

from content.config import BUNDLED_SEED_DIR, Config
from content.seed import load_seed_if_empty

URL = "mssql://content_svc:pw@sqlserver:1433/content"


# ----- config -----

def test_config_reads_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("PORT", "9001")
    monkeypatch.setenv("CORS_ORIGIN", "https://ui.example.net")
    monkeypatch.setenv("GIT_SHA", "abc123")
    monkeypatch.setenv("DB_RETRY_SECONDS", "5")
    config = Config.from_env()
    assert (config.database_url, config.port, config.cors_origin, config.git_sha, config.db_retry_seconds) == (
        URL, 9001, "https://ui.example.net", "abc123", 5)


def test_unset_variables_keep_their_defaults(monkeypatch):
    for name in ("PORT", "CORS_ORIGIN", "GIT_SHA", "DB_RETRY_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", URL)
    config = Config.from_env()
    assert (config.port, config.cors_origin, config.git_sha, config.db_retry_seconds) == (
        8000, "http://localhost:8080", "dev", 90)


def test_a_missing_database_url_stops_startup_with_a_clear_message(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        Config.from_env()


# ----- seed loader -----

@pytest.fixture
def seed_dir(tmp_path):
    folder = tmp_path / "seed"
    folder.mkdir()
    (folder / "sentences.tsv").write_text("El gato come.\tThe cat eats.\ttatoeba #1\n"
                                          "El perro come.\tThe dog eats.\ttatoeba #2\n", encoding="utf-8")
    (folder / "words.tsv").write_text("come\t1\ngato\t2\nperro\t3\n", encoding="utf-8")
    return folder


def test_seed_is_imported_with_ranks_into_an_empty_database(service, seed_dir):
    assert load_seed_if_empty(service, seed_dir) == 2
    assert [(w.headword, w.frequency_rank) for w in service.get_sentence(1).words] == [("come", 1), ("gato", 2)]


def test_seed_is_not_imported_twice(service, seed_dir):
    load_seed_if_empty(service, seed_dir)
    assert load_seed_if_empty(service, seed_dir) == 0
    assert service.count_sentences() == 2


def test_missing_seed_files_import_nothing(service, tmp_path):
    assert load_seed_if_empty(service, tmp_path / "nothing-here") == 0


def test_sentences_without_a_words_file_are_still_imported(service, seed_dir):
    (seed_dir / "words.tsv").unlink()
    assert load_seed_if_empty(service, seed_dir) == 2
    assert service.get_word(1).frequency_rank is None


def test_the_committed_seed_has_3000_sentences_in_five_tiers(service):
    from pathlib import Path
    assert load_seed_if_empty(service, Path(BUNDLED_SEED_DIR)) == 3000
    assert len(service.placement_quiz()) == 8
