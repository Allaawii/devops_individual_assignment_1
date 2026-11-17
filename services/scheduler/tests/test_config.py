"""Tests for reading the environment (scheduler.config)."""

import pytest

from scheduler.config import Config

URL = "mssql://scheduler_svc:pw@sqlserver:1433/scheduler"
OPTIONAL = ("PORT", "CORS_ORIGIN", "GIT_SHA", "DB_RETRY_SECONDS", "CONTENT_URL", "CONTENT_TIMEOUT_S",
            "SCHEDULER", "NEW_CARDS_PER_DAY")


def test_config_reads_the_environment(monkeypatch):
    values = {"DATABASE_URL": URL, "PORT": "9002", "CORS_ORIGIN": "https://ui.example.net", "GIT_SHA": "abc123",
              "DB_RETRY_SECONDS": "5", "CONTENT_URL": "https://content.example.net/", "CONTENT_TIMEOUT_S": "3.5",
              "SCHEDULER": "leitner", "NEW_CARDS_PER_DAY": "25"}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    config = Config.from_env()
    assert (config.database_url, config.port, config.cors_origin, config.git_sha, config.db_retry_seconds) == (
        URL, 9002, "https://ui.example.net", "abc123", 5)
    assert (config.content_url, config.content_timeout_s, config.scheduler, config.new_cards_per_day) == (
        "https://content.example.net", 3.5, "leitner", 25)     # the trailing slash is dropped


def test_unset_variables_keep_their_defaults(monkeypatch):
    for name in OPTIONAL:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", URL)
    config = Config.from_env()
    assert (config.port, config.cors_origin, config.content_url, config.content_timeout_s,
            config.scheduler, config.new_cards_per_day) == (8000, "http://localhost:8080", "http://content:8000",
                                                            2.0, "sm2", 15)


def test_a_missing_database_url_stops_startup_with_a_clear_message(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        Config.from_env()
