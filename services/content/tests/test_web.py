"""Tests for what every request gets: /health, CORS, the request log line and JSON errors."""

import logging

from tests.conftest import ORIGIN, VERSION


def test_health_is_ok_when_the_database_answers(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": VERSION}


def test_health_is_503_when_the_database_fails(client, db_check, caplog):
    db_check.error = ConnectionError("database paused")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json() == {"status": "error", "db": "error", "version": VERSION}
    assert "health check failed: ConnectionError" in caplog.text


def test_every_response_allows_only_the_ui_origin(client):
    headers = client.get("/health").headers
    assert headers["Access-Control-Allow-Origin"] == ORIGIN
    assert headers["Vary"] == "Origin"
    assert "PUT" in headers["Access-Control-Allow-Methods"]
    assert headers["Access-Control-Allow-Headers"] == "Content-Type"


def test_preflight_is_answered_with_204_and_the_cors_headers(client):
    response = client.options("/words/1/meaning")
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN


def test_each_request_logs_method_path_status_and_duration(client, caplog):
    caplog.set_level(logging.INFO, logger="content")
    client.get("/sentences/99?page=2")
    line = caplog.records[-1].getMessage()
    assert line.startswith("GET /sentences/99 404 ") and line.endswith("ms")  # no query string


def test_unknown_path_is_a_json_404(client):
    response = client.get("/nothing-here")
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_wrong_method_is_a_json_405(client):
    response = client.delete("/sentences")
    assert response.status_code == 405
    assert response.get_json()["error"] == "method_not_allowed"


def test_a_crash_is_a_json_500(client, service, monkeypatch):
    def broken() -> int:
        raise RuntimeError("boom")
    monkeypatch.setattr(service, "count_sentences", broken)
    response = client.get("/sentences")
    assert response.status_code == 500
    assert response.get_json()["error"] == "internal_error"
