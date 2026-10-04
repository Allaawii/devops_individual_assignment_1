"""Shared test fixtures."""

import sqlite3
from collections.abc import Callable, Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient

from trainer import create_app
from trainer.config import Config
from trainer.db import connect, init_db


@pytest.fixture
def conn(tmp_path) -> Iterator[sqlite3.Connection]:
    """A fresh SQLite database with the full schema, deleted after the test."""
    connection = connect(tmp_path / "test.db")
    init_db(connection)
    yield connection
    connection.close()


@pytest.fixture
def app(tmp_path) -> Flask:
    """The real app on a fresh, empty database (no seed). DATA_DIR doesn't exist yet, so creating it is exercised too."""
    return create_app(Config(data_dir=str(tmp_path / "nested" / "data"), seed_dir=str(tmp_path / "no-seed")))


@pytest.fixture
def client(app) -> FlaskClient:
    """A browser stand-in that sends requests to the app."""
    return app.test_client()


@pytest.fixture
def add_sentence(client) -> Callable:
    """Submit the add-sentence form, as a learner would."""
    def post(spanish: str = "El gato come.", english: str = "The cat eats.", note: str = ""):
        return client.post("/sentences/new", data={"spanish": spanish, "english": english, "grammar_note": note})
    return post
