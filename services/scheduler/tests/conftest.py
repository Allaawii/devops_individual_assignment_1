"""Shared test fixtures.

Most tests use in-memory fakes and need nothing installed. The SQL Server fixtures read
TEST_DATABASE_URL (CI always sets it); when it is not set, the tests that use them are skipped,
unless REQUIRE_SQL_TESTS is set (as in CI), which turns the skip into a failure.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from migrate import migrate
from scheduler import db
from scheduler.algorithms import SM2Strategy
from scheduler.config import MIGRATIONS_DIR
from scheduler.service import ReviewService
from scheduler.web import create_web_app
from tests.fakes import FakeCardRepository, FakeContentClient, FakeReviewLog, FakeSettingsStore

ORIGIN = "http://localhost:8080"
VERSION = "test-sha"
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


class FakeDbCheck:
    """Stands in for db.check_health: does nothing, or raises `error` when a test sets one."""

    def __init__(self) -> None:
        self.error: Exception | None = None

    def __call__(self) -> None:
        if self.error is not None:
            raise self.error


@pytest.fixture
def db_check() -> FakeDbCheck:
    return FakeDbCheck()


@pytest.fixture
def app(service, db_check) -> Flask:
    """The web app around the service with fake repositories and a fake content service."""
    return create_web_app(service, cors_origin=ORIGIN, version=VERSION, check_db=db_check)


@pytest.fixture
def client(app) -> FlaskClient:
    return app.test_client()


# ----- SQL Server -----

@pytest.fixture
def database_url() -> str:
    if not TEST_DATABASE_URL:
        if os.environ.get("REQUIRE_SQL_TESTS"):   # set in CI: a skipped SQL Server test would hide a gap
            pytest.fail("REQUIRE_SQL_TESTS is set but TEST_DATABASE_URL is not")
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
