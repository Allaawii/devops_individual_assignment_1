"""Tests for the whole startup (connect, migrate, seed, serve) against SQL Server.

Skipped when TEST_DATABASE_URL is not set; CI always sets it.
"""

import logging

import pytest

from app import create_app
from content.config import BUNDLED_SEED_DIR, Config

ATTRIBUTION = "CC-BY 2.0 (France) Attribution: tatoeba.org #1 (a) & #2 (b)"


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


def _start(database_url: str, seed_dir) -> object:
    return create_app(Config(database_url=database_url, seed_dir=str(seed_dir), git_sha="abc123"))


def test_first_start_migrates_seeds_and_serves(empty_database, seed_dir, caplog):
    caplog.set_level(logging.INFO)
    client = _start(empty_database, seed_dir).test_client()
    assert "migration applied: 001_init" in caplog.text
    assert "seed: imported 2 sentences" in caplog.text
    assert client.get("/health").get_json() == {"status": "ok", "db": "ok", "version": "abc123"}
    body = client.get("/sentences/1").get_json()
    assert body["sentence"]["source"] == ATTRIBUTION
    assert [(w["headword"], w["frequency_rank"]) for w in body["words"]] == [("come", 1), ("gato", 2)]


def test_a_second_start_applies_nothing_and_does_not_seed_again(empty_database, seed_dir, caplog):
    _start(empty_database, seed_dir)
    caplog.clear()
    caplog.set_level(logging.INFO)
    client = _start(empty_database, seed_dir).test_client()
    assert "migrations: nothing to apply" in caplog.text
    assert "seed:" not in caplog.text
    assert client.get("/sentences").get_json()["total"] == 2


def test_writes_through_the_api_are_committed(empty_database, tmp_path):
    client = _start(empty_database, tmp_path / "no-seed").test_client()
    assert client.post("/sentences", json={"spanish": "Hola", "english": "Hello"}).status_code == 201
    assert client.get("/sentences/1").status_code == 200   # a new request, so a new connection


def test_the_committed_seed_loads_3000_sentences_and_a_quiz(empty_database):
    client = _start(empty_database, BUNDLED_SEED_DIR).test_client()
    assert client.get("/sentences").get_json()["total"] == 3000
    assert len(client.get("/placement/quiz").get_json()["questions"]) == 8
