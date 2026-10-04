"""SQLite connection handling: one connection and one transaction per request."""

import sqlite3
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from flask import Flask, current_app, g

DB_FILENAME = "trainer.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
IN_BATCH_SIZE = 500  # well under SQLite's oldest limit of 999 placeholders per statement

GetConnection = Callable[[], sqlite3.Connection]


class SqliteRepository:
    """Base class for every SQLite repository: the connection getter plus small query helpers.

    It takes a function instead of a connection, so a repository can be built once in
    create_app() and still use the current request's connection. Repositories never commit;
    close_db() does that at the end of the request.
    """

    def __init__(self, get_conn: GetConnection) -> None:
        self._get_conn = get_conn

    def _execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def _execute_many(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        self._get_conn().executemany(sql, rows)

    def _fetch_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self._execute(sql, params).fetchone()

    def _fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self._execute(sql, params).fetchall()

    def _scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        """The first value of the first row, e.g. the result of COUNT(*)."""
        return self._fetch_one(sql, params)[0]

    def _fetch_all_in(self, sql: str, ids: Sequence[int]) -> list[sqlite3.Row]:
        """Run `sql`, whose `{ids}` marks an `IN (...)` list, for any number of ids.

        SQLite limits how many ? placeholders one statement may have, so the ids are sent in batches.
        """
        rows: list[sqlite3.Row] = []
        for start in range(0, len(ids), IN_BATCH_SIZE):
            batch = ids[start:start + IN_BATCH_SIZE]
            rows += self._fetch_all(sql.format(ids=", ".join("?" * len(batch))), batch)
        return rows


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection that returns rows as dict-like objects and enforces foreign keys."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes. Safe to run on every start (IF NOT EXISTS)."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def get_db() -> sqlite3.Connection:
    """Return the current request's connection, opening it on first use."""
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(error: BaseException | None = None) -> None:
    """Teardown: commit if the request succeeded, roll back if it raised, then close."""
    conn = g.pop("db", None)
    if conn is None:
        return
    try:
        if error is None:
            conn.commit()
        else:
            conn.rollback()
    finally:
        conn.close()


def init_app(app: Flask, data_dir: str) -> None:
    """Create DATA_DIR if missing, register the teardown, and create the schema."""
    directory = Path(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    app.config["DB_PATH"] = str(directory / DB_FILENAME)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db(get_db())
