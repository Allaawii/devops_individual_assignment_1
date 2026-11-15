"""SQL Server connections: reading DATABASE_URL, connecting with retries at startup,
and one connection and one transaction per request (same idea as Assignment 1)."""

import logging
import time
from collections.abc import Callable, Iterator, Sequence
from typing import Any
from urllib.parse import unquote, urlparse

import pymssql
from flask import Flask, current_app, g

log = logging.getLogger("content")

Connection = Any                    # a pymssql connection; rows come back as dicts (as_dict=True)
GetConnection = Callable[[], Connection]

LOGIN_TIMEOUT_S = 10                # one connection attempt
QUERY_TIMEOUT_S = 30                # one statement
MAX_RETRY_DELAY_S = 30
ROWS_PER_BATCH = 400                # rows per multi-row INSERT, or ids per IN list: well under the
                                    # 1,000-row limit of one VALUES list. pymssql fills in %s itself,
                                    # so the 2,100-parameter limit of RPC calls does not apply.


def parse_database_url(url: str) -> dict[str, str]:
    """Turn mssql://user:password@host:1433/database into pymssql.connect() arguments.

    The user and password may be percent-encoded (e.g. %40 for @), so they are decoded.
    """
    parts = urlparse(url)
    database = parts.path.lstrip("/")
    if parts.scheme != "mssql" or not parts.hostname or not database:
        raise ValueError("DATABASE_URL must look like mssql://user:password@host:1433/database")
    return {
        "server": parts.hostname,
        "port": str(parts.port or 1433),
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "database": database,
    }


def connect(url: str) -> Connection:
    """Open one connection. Autocommit is off, so every change waits for commit()."""
    return pymssql.connect(**parse_database_url(url), as_dict=True, tds_version="7.4", charset="UTF-8",
                           login_timeout=LOGIN_TIMEOUT_S, timeout=QUERY_TIMEOUT_S)


def retry_delays(max_seconds: int) -> list[int]:
    """Waits between connection attempts: 1, 2, 4, 8, 16, 30, 30, ... seconds, adding up to max_seconds.

    The last wait is shortened so the total is exactly max_seconds (90 s gives 1, 2, 4, 8, 16, 30, 29).
    """
    delays: list[int] = []
    delay = 1
    while sum(delays) < max_seconds:
        delays.append(min(delay, max_seconds - sum(delays)))
        delay = min(delay * 2, MAX_RETRY_DELAY_S)
    return delays


def connect_with_retry(url: str, max_seconds: int, open_connection: Callable[[str], Connection] = connect,
                       sleep: Callable[[float], None] = time.sleep) -> Connection:
    """Connect, retrying while the database is unreachable (e.g. Azure SQL resuming: error 40613).

    After the last wait, one final attempt is made and its error reaches the caller, so a
    database that never comes up still stops the service with a clear error.
    """
    for delay in retry_delays(max_seconds):
        try:
            return open_connection(url)
        except pymssql.Error as error:
            log.warning("database not reachable yet (%s), retrying in %d s", type(error).__name__, delay)
            sleep(delay)
    return open_connection(url)


def batches(items: Sequence[Any], size: int | None = None) -> Iterator[Sequence[Any]]:
    """Consecutive slices of at most `size` items (default ROWS_PER_BATCH, read at call time)."""
    size = size or ROWS_PER_BATCH
    for start in range(0, len(items), size):
        yield items[start:start + size]


class MssqlRepository:
    """Base class for every repository: the connection getter plus small query helpers.

    It takes a function instead of a connection, so a repository can be built once at startup
    and still use the current request's connection. Repositories never commit; close_db() does.
    """

    def __init__(self, get_conn: GetConnection) -> None:
        self._get_conn = get_conn

    def _execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        cursor = self._get_conn().cursor()
        cursor.execute(sql, tuple(params) if params else None)  # None: no %s substitution at all
        return cursor

    def _fetch_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        return self._execute(sql, params).fetchone()

    def _fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return self._execute(sql, params).fetchall()

    def _scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        """The first value of the first row, e.g. COUNT(*). The column needs a name (AS n)."""
        return next(iter(self._fetch_one(sql, params).values()))

    def _insert_many(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        """Insert many rows with a few multi-row INSERTs, keeping identity ids in the order given.

        SQL Server only promises identity order for INSERT ... SELECT ... ORDER BY, so each batch
        is sent as a VALUES list with a position column and inserted in position order.
        """
        names = ", ".join(columns)
        for batch in batches(rows):
            row_marks = ", ".join("(" + ", ".join(["%s"] * (len(columns) + 1)) + ")" for _ in batch)
            values = [value for position, row in enumerate(batch) for value in (position, *row)]
            self._execute(f"INSERT INTO {table} ({names}) SELECT {names} "
                          f"FROM (VALUES {row_marks}) AS v (position, {names}) ORDER BY position", values)

    def _fetch_all_in(self, sql: str, ids: Sequence[int]) -> list[dict[str, Any]]:
        """Run `sql`, whose `{ids}` marks an `IN (...)` list, for any number of ids, in batches."""
        rows: list[dict[str, Any]] = []
        for batch in batches(ids):
            rows += self._fetch_all(sql.format(ids=", ".join(["%s"] * len(batch))), batch)
        return rows


def get_db() -> Connection:
    """Return the current request's connection, opening it on first use."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_URL"])
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


def check_health() -> None:
    """Prove the database can be read and written: SELECT 1, then touch the health_check row.

    Raises whatever the driver raises; the /health route turns that into a 503.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 AS ok")
    cursor.fetchone()
    cursor.execute("UPDATE health_check SET checked_at = SYSUTCDATETIME() WHERE id = 1")
    conn.commit()


def init_app(app: Flask, database_url: str) -> None:
    """Remember where the database is and register the per-request teardown."""
    app.config["DATABASE_URL"] = database_url
    app.teardown_appcontext(close_db)
