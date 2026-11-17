"""Tests for HttpContentClient with a recording stand-in for requests.request: no network needed."""

import pytest
import requests

from scheduler.content_client import SCORE_TIMEOUT_S, ContentUnavailable, FeedItem, HttpContentClient, Placement

BASE = "http://content:8000"


class FakeResponse:
    def __init__(self, status_code: int, body=None, text_only: bool = False) -> None:
        self.status_code = status_code
        self._body = body
        self._text_only = text_only

    def json(self):
        if self._text_only:
            raise ValueError("not JSON")
        return self._body


class FakeHttp:
    """Answers every request with `response` (or raises `error`) and records how it was called."""

    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or FakeResponse(200, {})
        self.error = error
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def _client(http: FakeHttp, timeout: float = 2.0) -> HttpContentClient:
    return HttpContentClient(BASE + "/", timeout, http=http)


# ----- happy paths -----

def test_feed_sends_after_id_and_limit_with_the_timeout():
    http = FakeHttp(FakeResponse(200, {"items": [{"id": 4, "word_ids": [7, 9]}]}))
    assert _client(http).feed(3, 20) == [FeedItem(4, [7, 9])]
    assert http.calls == [("GET", f"{BASE}/sentences/feed", {"timeout": 2.0, "params": {"after_id": 3, "limit": 20}})]


def test_sentence_and_word_return_contents_json_bodies():
    http = FakeHttp(FakeResponse(200, {"sentence": {"id": 5}}))
    client = _client(http)
    assert client.sentence(5) == {"sentence": {"id": 5}}
    client.word(8)
    assert [url for _, url, _ in http.calls] == [f"{BASE}/sentences/5", f"{BASE}/words/8"]


def test_score_posts_the_answers_with_the_longer_timeout():
    http = FakeHttp(FakeResponse(200, {"level": 1, "level_name": "Beginner", "sentence_ids": [1], "word_ids": [2]}))
    assert _client(http).score({"q1": "a"}) == Placement(1, "Beginner", [1], [2])
    method, url, kwargs = http.calls[0]
    assert (method, url) == ("POST", f"{BASE}/placement/score")
    assert kwargs == {"timeout": SCORE_TIMEOUT_S, "json": {"answers": {"q1": "a"}}}


# ----- every failure becomes ContentUnavailable -----

@pytest.mark.parametrize("error", [requests.Timeout("slow"), requests.ConnectionError("refused")])
def test_timeouts_and_connection_errors_become_content_unavailable(error):
    with pytest.raises(ContentUnavailable, match=type(error).__name__):
        _client(FakeHttp(error=error)).sentence(1)


@pytest.mark.parametrize("status", [404, 500, 503])
def test_an_error_status_becomes_content_unavailable(status):
    with pytest.raises(ContentUnavailable, match=f"content answered {status}"):
        _client(FakeHttp(FakeResponse(status, {"error": "x"}))).word(1)


def test_a_body_that_is_not_json_becomes_content_unavailable():
    with pytest.raises(ContentUnavailable, match="not JSON"):
        _client(FakeHttp(FakeResponse(200, text_only=True))).feed(0, 20)


def test_the_call_is_tried_only_once():
    http = FakeHttp(error=requests.Timeout("slow"))
    with pytest.raises(ContentUnavailable):
        _client(http).feed(0, 20)
    assert len(http.calls) == 1
