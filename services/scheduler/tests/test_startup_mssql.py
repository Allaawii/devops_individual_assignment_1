"""Tests for the whole startup (connect, migrate, serve) against SQL Server, with content not running.

Skipped when TEST_DATABASE_URL is not set; CI always sets it. The content URL points at a port
where nothing listens, which is exactly the "content is down" case.
"""

import logging

import pytest

from app import create_app
from scheduler.config import Config

NOWHERE = "http://127.0.0.1:9"   # the discard port: nothing answers there


def _start(database_url: str, scheduler: str = "sm2"):
    return create_app(Config(database_url=database_url, content_url=NOWHERE, content_timeout_s=0.5,
                             git_sha="abc123", scheduler=scheduler))


def test_first_start_migrates_and_serves_its_own_data_without_content(empty_database, caplog):
    caplog.set_level(logging.INFO)
    client = _start(empty_database).test_client()
    assert "migration applied: 001_init" in caplog.text
    assert client.get("/health").get_json() == {"status": "ok", "db": "ok", "version": "abc123"}
    assert client.put("/goal", json={"goal": 12}).status_code == 200
    assert client.get("/stats").get_json()["goal"] == 12                     # committed by the teardown
    assert client.get("/review/next").status_code == 503                     # content is down


def test_a_second_start_applies_nothing(empty_database, caplog):
    _start(empty_database)
    caplog.clear()
    caplog.set_level(logging.INFO)
    _start(empty_database)
    assert "migrations: nothing to apply" in caplog.text


def test_an_unknown_scheduler_stops_startup(empty_database):
    with pytest.raises(ValueError, match="Unknown SCHEDULER"):
        _start(empty_database, scheduler="random")
