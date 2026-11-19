"""Partial failure, run after `docker compose stop content` (pytest -m content_down).

The scheduler must keep serving its own domain, and the flows that need content must fail in
the designed way: a quick 503 content_unavailable, not a stack trace or a hung request.
"""

import time

import pytest
import requests

pytestmark = pytest.mark.content_down

TIMEOUT = 10
DESIGNED_FAILURE_SECONDS = 5   # CONTENT_TIMEOUT_S is 2; the answer must come well before the browser gives up


def test_content_is_really_stopped(content_url):
    with pytest.raises(requests.ConnectionError):
        requests.get(content_url + "/health", timeout=3)


def test_review_answers_the_designed_503_quickly(scheduler_url):
    started = time.monotonic()
    response = requests.get(scheduler_url + "/review/next", timeout=TIMEOUT)
    assert time.monotonic() - started < DESIGNED_FAILURE_SECONDS
    assert response.status_code == 503
    assert response.json()["error"] == "content_unavailable"
    assert "progress is safe" in response.json()["message"]


def test_quiz_scoring_answers_the_designed_503(scheduler_url):
    response = requests.post(scheduler_url + "/placement", json={"answers": {"q1": "x"}}, timeout=TIMEOUT)
    assert response.status_code == 503
    assert response.json()["error"] == "content_unavailable"


def test_the_scheduler_keeps_serving_its_own_domain(scheduler_url):
    assert requests.get(scheduler_url + "/health", timeout=TIMEOUT).json()["status"] == "ok"   # its own state only
    assert requests.get(scheduler_url + "/stats", timeout=TIMEOUT).status_code == 200
    assert requests.put(scheduler_url + "/goal", json={"goal": 12}, timeout=TIMEOUT).json() == {"goal": 12}
    skipped = requests.post(scheduler_url + "/placement", json={"skip": True}, timeout=TIMEOUT)
    assert skipped.status_code == 200
