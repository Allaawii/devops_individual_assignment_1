"""Shared test fixtures.

Most tests use in-memory fakes and need nothing installed. The SQL Server fixtures read
TEST_DATABASE_URL (CI always sets it); when it is not set, the tests that use them are skipped.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from migrate import migrate
from scheduler import db
from scheduler.algorithms import SM2Strategy
from scheduler.config import MIGRATIONS_DIR
from scheduler.service import ReviewService
from tests.fakes import FakeCardRepository, FakeContentClient, FakeReviewLog, FakeSettingsStore

DEFAULT_LIMIT = 15
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
SCHEDULER_TABLES = ("reviews", "cards", "settings", "health_check", "schema_migrations")  # FK order


# ----- fakes -----

@pytest.fixture
def cards() -> FakeCardRepository:
    return FakeCardRepository()


@pytest.fixture
def log() -> FakeReviewLog:
    return FakeReviewLog()


@pytest.fixture
def settings() -> FakeSettingsStore:
    return FakeSettingsStore()


@pytest.fixture
def content() -> FakeContentClient:
    return FakeContentClient()


@pytest.fixture
def service(cards, log, settings, content) -> ReviewService:
    return ReviewService(cards, log, settings, SM2Strategy(), DEFAULT_LIMIT, content)


# ----- SQL Server -----

@pytest.fixture
def database_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set: SQL Server tests run in CI or against the compose database")
    return TEST_DATABASE_URL


@pytest.fixture
def empty_database(database_url) -> str:
    """Drop every scheduler table, so the test starts from a database with nothing in it."""
    conn = db.connect(database_url)
    try:
        conn.cursor().execute("DROP TABLE IF EXISTS " + ", ".join(SCHEDULER_TABLES))
        conn.commit()
    finally:
        conn.close()
    return database_url


@pytest.fixture
def conn(empty_database) -> Iterator[db.Connection]:
    """A connection to a freshly migrated database. Closing it rolls back what the test did not commit."""
    connection = db.connect(empty_database)
    migrate(connection, Path(MIGRATIONS_DIR))
    yield connection
    connection.close()
