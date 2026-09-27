"""SQLite connection handling: one connection and one transaction per request."""

import sqlite3
from pathlib import Path

from flask import Flask, current_app, g

DB_FILENAME = "trainer.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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
