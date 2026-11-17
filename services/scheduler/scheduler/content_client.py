"""How the scheduler talks to the content service: the only place that knows content's URLs.

ReviewService depends on the abstract ContentClient, so its tests use a fake. HttpContentClient
is the real one. Every call has a timeout and is tried once: a learner waiting on a page should
get a quick, clear error rather than a long wait (ADR-6). Anything that goes wrong (timeout, no
connection, an error status, a body that is not JSON) becomes ContentUnavailable.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import requests

SCORE_TIMEOUT_S = 5.0   # scoring reads the whole seed, so it may take longer than a single lookup


class ContentUnavailable(Exception):
    """The content service did not give a usable answer. The API turns this into a designed 503."""


@dataclass(frozen=True)
class FeedItem:
    """A sentence the scheduler has no card for yet, with the ids of its words."""

    id: int
    word_ids: list[int]


@dataclass(frozen=True)
class Placement:
    """The scored placement quiz: the level and the seed material below it."""

    level: int
    level_name: str
    sentence_ids: list[int]
    word_ids: list[int]


class ContentClient(ABC):
    @abstractmethod
    def feed(self, after_id: int, limit: int) -> list[FeedItem]:
        """The next sentences after `after_id`, in id order (the pull)."""

    @abstractmethod
    def sentence(self, sentence_id: int) -> dict[str, Any]:
        """Content's GET /sentences/{id} body: the sentence, its words and key words."""

    @abstractmethod
    def word(self, word_id: int) -> dict[str, Any]:
        """Content's GET /words/{id} body: the word and up to 3 example sentences."""

    @abstractmethod
    def score(self, answers: Mapping[str, str]) -> Placement:
        """Score the placement quiz answers."""


Http = Callable[..., requests.Response]   # the shape of requests.request, so tests can pass a fake


class HttpContentClient(ContentClient):
    def __init__(self, base_url: str, timeout_s: float, http: Http = requests.request) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._http = http

    def feed(self, after_id: int, limit: int) -> list[FeedItem]:
        body = self._call("GET", "/sentences/feed", params={"after_id": after_id, "limit": limit})
        return [FeedItem(item["id"], item["word_ids"]) for item in body["items"]]

    def sentence(self, sentence_id: int) -> dict[str, Any]:
        return self._call("GET", f"/sentences/{sentence_id}")

    def word(self, word_id: int) -> dict[str, Any]:
        return self._call("GET", f"/words/{word_id}")

    def score(self, answers: Mapping[str, str]) -> Placement:
        body = self._call("POST", "/placement/score", json={"answers": dict(answers)},
                          timeout=max(self._timeout_s, SCORE_TIMEOUT_S))
        return Placement(body["level"], body["level_name"], body["sentence_ids"], body["word_ids"])

    def _call(self, method: str, path: str, timeout: float | None = None, **kwargs: Any) -> Any:
        """Send one request and return its JSON body, or raise ContentUnavailable.

        A 404 is also ContentUnavailable: content never deletes, so a missing id means the two
        databases are out of step, and the learner can do nothing about it but wait for a fix.
        """
        try:
            response = self._http(method, self._base_url + path, timeout=timeout or self._timeout_s, **kwargs)
        except requests.RequestException as error:   # timeout, refused connection, DNS failure, ...
            raise ContentUnavailable(f"{method} {path}: {type(error).__name__}") from error
        if response.status_code != 200:
            raise ContentUnavailable(f"{method} {path}: content answered {response.status_code}")
        try:
            return response.json()
        except ValueError as error:                  # the body is not JSON
            raise ContentUnavailable(f"{method} {path}: the answer was not JSON") from error
