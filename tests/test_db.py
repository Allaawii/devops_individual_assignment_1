"""Tests for schema.sql and the per-request transaction handling in db.py."""

import sqlite3

import pytest

from trainer import create_app
from trainer.config import Config
from trainer.db import connect, get_db, init_db

TABLES = {"sentences", "words", "sentence_words", "cards", "reviews"}
INSERT_SENTENCE = (
    "INSERT INTO sentences (spanish_text, english_text, source, created_at) "
    "VALUES ('Hola', 'Hello', 'user', '2026-09-27T10:00:00')"
)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row["name"] for row in rows}


def _sentence_count(db_path: str) -> int:
    conn = connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    finally:
        conn.close()


# ----- schema -----

def test_init_db_creates_all_tables(conn):
    assert TABLES <= _table_names(conn)


def test_init_db_is_safe_to_run_twice(conn):
    init_db(conn)
    assert TABLES <= _table_names(conn)


def test_foreign_keys_are_enforced(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO sentence_words (sentence_id, word_id) VALUES (999, 999)")


def test_card_with_both_ids_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO cards (card_type, word_id, sentence_id) VALUES ('word', 1, 1)"
        )


def test_word_card_without_word_id_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO cards (card_type, sentence_id) VALUES ('word', 1)")


def test_duplicate_word_card_is_rejected(conn):
    conn.execute("INSERT INTO cards (card_type, word_id) VALUES ('word', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO cards (card_type, word_id) VALUES ('word', 1)")


def test_many_sentence_cards_can_share_a_null_word_id(conn):
    conn.execute("INSERT INTO cards (card_type, sentence_id) VALUES ('sentence', 1)")
    conn.execute("INSERT INTO cards (card_type, sentence_id) VALUES ('sentence', 2)")
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 2


def test_review_quality_outside_0_to_5_is_rejected(conn):
    conn.execute("INSERT INTO cards (card_type, word_id) VALUES ('word', 1)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reviews (card_id, reviewed_at, quality, resulting_interval, resulting_ease) "
            "VALUES (1, '2026-09-27T10:00:00', 6, 1, 2.5)"
        )


# ----- app wiring and transactions -----

@pytest.fixture
def app(tmp_path):
    return create_app(Config(data_dir=str(tmp_path / "nested" / "data")))


def test_create_app_creates_database_under_data_dir(app, tmp_path):
    assert (tmp_path / "nested" / "data" / "trainer.db").exists()


def test_successful_request_commits(app):
    with app.app_context():
        get_db().execute(INSERT_SENTENCE)
    assert _sentence_count(app.config["DB_PATH"]) == 1


def test_failed_request_rolls_back(app):
    with pytest.raises(RuntimeError):
        with app.app_context():
            get_db().execute(INSERT_SENTENCE)
            raise RuntimeError("request failed")
    assert _sentence_count(app.config["DB_PATH"]) == 0


def test_same_connection_is_reused_within_a_request(app):
    with app.app_context():
        assert get_db() is get_db()
