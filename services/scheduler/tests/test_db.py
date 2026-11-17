"""Tests for scheduler.db that need no database: URL parsing, retries, batching and the request teardown."""

import pymssql
import pytest
from flask import Flask, g

from scheduler import db


class RecordingConnection:
    """A stand-in connection that records every statement and whether it committed or rolled back."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple | None]] = []
        self.events: list[str] = []

    def cursor(self) -> "RecordingConnection":
        return self

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.statements.append((sql, params))

    def fetchone(self) -> dict:
        return {"n": 7}

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


# ----- DATABASE_URL -----

def test_database_url_is_split_into_connect_arguments():
    assert db.parse_database_url("mssql://scheduler_svc:s3cret@sqlserver:1433/scheduler") == {
        "server": "sqlserver", "port": "1433", "user": "scheduler_svc", "password": "s3cret", "database": "scheduler",
    }


def test_percent_encoded_password_is_decoded_and_port_defaults_to_1433():
    parts = db.parse_database_url("mssql://u:p%40ss%3Aword@db.example.net/app")
    assert (parts["password"], parts["port"]) == ("p@ss:word", "1433")


@pytest.mark.parametrize("url", ["", "postgres://u:p@h/db", "mssql://u:p@h:1433/", "mssql:///db"])
def test_bad_database_url_is_rejected_with_the_expected_format(url):
    with pytest.raises(ValueError, match="mssql://user:password@host:1433/database"):
        db.parse_database_url(url)


# ----- retries -----

def test_retry_delays_double_up_to_30_seconds_and_add_up_to_the_budget():
    assert db.retry_delays(90) == [1, 2, 4, 8, 16, 30, 29]
    assert sum(db.retry_delays(200)) == 200
    assert db.retry_delays(0) == []


def test_connect_with_retry_waits_until_the_database_answers(caplog):
    attempts, waits = [], []

    def open_connection(url):
        attempts.append(url)
        if len(attempts) < 3:
            raise pymssql.OperationalError(40613, b"Database is not currently available")
        return "connection"

    assert db.connect_with_retry("mssql://x", 90, open_connection, waits.append) == "connection"
    assert waits == [1, 2]
    assert "database not reachable yet (OperationalError), retrying in 1 s" in caplog.text


def test_connect_with_retry_gives_up_after_the_budget_with_the_last_error():
    waits = []

    def never(url):
        raise pymssql.OperationalError("down")

    with pytest.raises(pymssql.OperationalError):
        db.connect_with_retry("mssql://x", 7, never, waits.append)
    assert waits == [1, 2, 4]


def test_batches_cut_a_list_into_slices():
    assert list(db.batches([1, 2, 3, 4, 5], size=2)) == [[1, 2], [3, 4], [5]]
    assert list(db.batches([], size=2)) == []


# ----- repository helpers -----

def test_insert_many_sends_batches_in_position_order(monkeypatch):
    monkeypatch.setattr(db, "ROWS_PER_BATCH", 2)
    conn = RecordingConnection()
    db.MssqlRepository(lambda: conn)._insert_many("words", ("headword", "frequency_rank"),
                                                  [("a", 1), ("b", None), ("c", 3)])
    (first_sql, first_params), (_, second_params) = conn.statements
    assert first_sql == ("INSERT INTO words (headword, frequency_rank) SELECT headword, frequency_rank "
                         "FROM (VALUES (%s, %s, %s), (%s, %s, %s)) AS v (position, headword, frequency_rank) "
                         "ORDER BY position")
    assert first_params == (0, "a", 1, 1, "b", None)
    assert second_params == (0, "c", 3)


def test_query_without_parameters_is_sent_without_substitution():
    conn = RecordingConnection()
    assert db.MssqlRepository(lambda: conn)._scalar("SELECT COUNT(*) AS n FROM words") == 7
    assert conn.statements == [("SELECT COUNT(*) AS n FROM words", None)]


def test_fetch_all_in_sends_no_query_for_no_ids():
    conn = RecordingConnection()
    assert db.MssqlRepository(lambda: conn)._fetch_all_in("SELECT 1 WHERE id IN ({ids})", []) == []
    assert conn.statements == []


# ----- per-request connection -----

@pytest.fixture
def flask_app(monkeypatch) -> tuple[Flask, list[RecordingConnection]]:
    opened: list[RecordingConnection] = []

    def fake_connect(url):
        opened.append(RecordingConnection())
        return opened[-1]

    monkeypatch.setattr(db, "connect", fake_connect)
    app = Flask(__name__)
    db.init_app(app, "mssql://u:p@h/db")
    return app, opened


def test_one_connection_per_request_committed_at_the_end(flask_app):
    app, opened = flask_app
    with app.app_context():
        assert db.get_db() is db.get_db()
    assert len(opened) == 1
    assert opened[0].events == ["commit", "close"]


def test_a_failed_request_is_rolled_back(flask_app):
    app, opened = flask_app
    ctx = app.app_context()
    ctx.push()
    db.get_db()
    ctx.pop(RuntimeError("boom"))
    assert opened[0].events == ["rollback", "close"]


def test_teardown_without_a_connection_does_nothing(flask_app):
    app, opened = flask_app
    with app.app_context():
        assert "db" not in g
    assert opened == []


def test_check_health_reads_writes_and_commits(flask_app):
    app, opened = flask_app
    with app.app_context():
        db.check_health()
    sql = [statement for statement, _ in opened[0].statements]
    assert sql[0] == "SELECT 1 AS ok"
    assert sql[1].startswith("UPDATE health_check")
    assert opened[0].events[0] == "commit"
