"""Tests for the migration runner (migrate.py): first with a recording stand-in connection,
then against SQL Server (skipped without TEST_DATABASE_URL)."""

import logging
from pathlib import Path

import pymssql
import pytest

from content import db
from content.config import MIGRATIONS_DIR
from migrate import migrate, pending, split_batches


class FakeMigrationConnection:
    """Records statements; `applied` plays the schema_migrations table; `fail_on` makes one statement fail."""

    def __init__(self, applied: list[str] | None = None, fail_on: str | None = None) -> None:
        self.applied = applied or []
        self.fail_on = fail_on
        self.statements: list[str] = []
        self.events: list[str] = []

    def cursor(self) -> "FakeMigrationConnection":
        return self

    def execute(self, sql: str, params: tuple | None = None) -> None:
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError(f"cannot run: {sql}")
        self.statements.append(sql)

    def fetchall(self) -> list[dict]:
        return [{"version": version} for version in self.applied]

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")


@pytest.fixture
def migrations(tmp_path) -> Path:
    (tmp_path / "002_second.sql").write_text("ALTER TABLE t ADD c INT;\nGO\nUPDATE t SET c = 1;\n", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("CREATE TABLE t (id INT);\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a migration", encoding="utf-8")
    return tmp_path


# ----- splitting and ordering -----

def test_script_is_split_on_go_lines_only():
    script = "CREATE TABLE a (id INT);\ngo\n  GO  \nSELECT 'GO' AS word;\nINSERT INTO a VALUES (1); -- GOod\n"
    assert split_batches(script) == ["CREATE TABLE a (id INT);",
                                     "SELECT 'GO' AS word;\nINSERT INTO a VALUES (1); -- GOod"]


def test_pending_lists_sql_files_in_name_order_without_applied_ones(migrations):
    assert [p.name for p in pending(migrations, set())] == ["001_first.sql", "002_second.sql"]
    assert [p.name for p in pending(migrations, {"001_first"})] == ["002_second.sql"]


# ----- running, with a stand-in connection -----

def test_each_pending_file_runs_with_its_version_row_then_commits(migrations, caplog):
    caplog.set_level(logging.INFO, logger="migrate")
    conn = FakeMigrationConnection()
    assert migrate(conn, migrations) == ["001_first", "002_second"]
    assert conn.statements[2:] == [
        "CREATE TABLE t (id INT);",
        "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, SYSUTCDATETIME())",
        "ALTER TABLE t ADD c INT;",
        "UPDATE t SET c = 1;",
        "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, SYSUTCDATETIME())",
    ]
    assert conn.events == ["commit", "commit", "commit"]   # the table check, then one per file
    assert "migration applied: 001_first" in caplog.text and "migration applied: 002_second" in caplog.text


def test_nothing_to_apply_is_logged(migrations, caplog):
    caplog.set_level(logging.INFO, logger="migrate")
    conn = FakeMigrationConnection(applied=["001_first", "002_second"])
    assert migrate(conn, migrations) == []
    assert "migrations: nothing to apply" in caplog.text


def test_a_failing_file_is_rolled_back_and_stops_the_run(migrations, caplog):
    conn = FakeMigrationConnection(applied=["001_first"], fail_on="UPDATE t")
    with pytest.raises(RuntimeError):
        migrate(conn, migrations)
    assert conn.events == ["commit", "rollback"]
    assert "migration failed: 002_second (rolled back)" in caplog.text


# ----- against SQL Server -----

def _tables(conn) -> set[str]:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sys.tables")
    return {row["name"] for row in cursor.fetchall()}


def test_001_creates_the_content_schema_once(empty_database, caplog):
    caplog.set_level(logging.INFO, logger="migrate")
    conn = db.connect(empty_database)
    try:
        assert migrate(conn, Path(MIGRATIONS_DIR)) == ["001_init", "002_add_sentence_level"]
        assert {"sentences", "words", "sentence_words", "health_check", "schema_migrations"} <= _tables(conn)
        assert migrate(conn, Path(MIGRATIONS_DIR)) == []
    finally:
        conn.close()
    assert "migration applied: 001_init" in caplog.text
    assert "migrations: nothing to apply" in caplog.text


def test_002_backfills_the_level_of_existing_seed_sentences(empty_database, tmp_path):
    """The data-changing migration on a database that already has rows, as on Azure."""
    only_001 = tmp_path / "only_001"
    only_001.mkdir()
    (only_001 / "001_init.sql").write_text((Path(MIGRATIONS_DIR) / "001_init.sql").read_text(encoding="utf-8"),
                                           encoding="utf-8")
    conn = db.connect(empty_database)
    try:
        migrate(conn, only_001)
        cursor = conn.cursor()
        for i in range(1, 11):          # 10 seed sentences, with one of the learner's own in the middle
            source = "user" if i == 4 else "tatoeba"
            cursor.execute("INSERT INTO sentences (spanish_text, english_text, source, created_at) "
                           "VALUES (%s, 'x', %s, SYSUTCDATETIME())", (f"frase {i}", source))
        conn.commit()
        assert migrate(conn, Path(MIGRATIONS_DIR)) == ["002_add_sentence_level"]
        cursor.execute("SELECT id, level FROM sentences ORDER BY id")
        levels = {row["id"]: row["level"] for row in cursor.fetchall()}
    finally:
        conn.close()
    # 9 seed sentences: positions 0-8 give 0,0,1,1,2,2,3,3,4 (position * 5 / 9); the learner's stays NULL.
    assert levels == {1: 0, 2: 0, 3: 1, 4: None, 5: 1, 6: 2, 7: 2, 8: 3, 9: 3, 10: 4}


def test_a_failing_migration_leaves_no_trace_in_sql_server(empty_database, tmp_path):
    (tmp_path / "001_broken.sql").write_text("CREATE TABLE half_done (id INT);\nGO\nSELECT * FROM missing;\n",
                                             encoding="utf-8")
    conn = db.connect(empty_database)
    try:
        with pytest.raises(pymssql.Error):     # "Invalid object name 'missing'"
            migrate(conn, tmp_path)
        assert "half_done" not in _tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM schema_migrations")
        assert cursor.fetchone()["n"] == 0
        cursor.execute("DROP TABLE IF EXISTS half_done")
        conn.commit()
    finally:
        conn.close()
