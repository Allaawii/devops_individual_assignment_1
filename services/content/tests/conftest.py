"""Shared test fixtures.

Most tests use in-memory fakes and need nothing installed. The SQL Server fixtures read
TEST_DATABASE_URL (CI always sets it); when it is not set, the tests that use them are skipped,
unless REQUIRE_SQL_TESTS is set (as in CI), which turns the skip into a failure.
"""

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from content import db
from content.config import MIGRATIONS_DIR
from content.service import ContentService
from content.web import create_web_app
from migrate import migrate
from tests.fakes import FakeSentenceRepository, FakeWordRepository

FIXED_NOW = datetime(2026, 11, 16, 10, 30, 0)
ORIGIN = "http://localhost:8080"
VERSION = "test-sha"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
CONTENT_TABLES = ("sentence_words", "sentences", "words", "health_check", "schema_migrations")  # FK order


# ----- fakes -----

@pytest.fixture
def sentence_repo() -> FakeSentenceRepository:
    return FakeSentenceRepository()


@pytest.fixture
def word_repo(sentence_repo) -> FakeWordRepository:
    return FakeWordRepository(sentence_repo.links)


@pytest.fixture
def service(sentence_repo, word_repo) -> ContentService:
    return ContentService(sentence_repo, word_repo, clock=lambda: FIXED_NOW)


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
    """The web app around the service with fake repositories."""
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
    """Drop every content table, so the test starts from a database with nothing in it."""
    conn = db.connect(database_url)
    try:
        conn.cursor().execute("DROP TABLE IF EXISTS " + ", ".join(CONTENT_TABLES))
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
