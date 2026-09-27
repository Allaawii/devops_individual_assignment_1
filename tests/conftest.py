"""Shared test fixtures."""

import sqlite3
from collections.abc import Iterator

import pytest

from trainer.db import connect, init_db


@pytest.fixture
def conn(tmp_path) -> Iterator[sqlite3.Connection]:
    """A fresh SQLite database with the full schema, deleted after the test."""
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    yield connection
    connection.close()
