"""Cross-seam tests: the real scheduler calling the real content service, each with its own
SQL Server database, as started by `docker compose up`. No stubs: this is the one place where
the HTTP contract between the two services is checked (the unit tests use a fake content client).

The tests run in file order and build on each other (the pull, then a rating), like a learner would.
"""

import requests

from conftest import UI_ORIGIN

TIMEOUT = 10


def _get(url: str) -> requests.Response:
    return requests.get(url, timeout=TIMEOUT)


def test_each_service_reports_its_own_health(content_url, scheduler_url):
    for base in (content_url, scheduler_url):
        response = _get(base + "/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok" and response.json()["db"] == "ok"


def test_content_imported_the_seed_on_first_start(content_url):
    assert _get(content_url + "/sentences").json()["total"] >= 3000


def test_review_pulls_from_content_and_shows_contents_text(content_url, scheduler_url):
    """Crosses the seam twice: the scheduler pulls the feed, then fetches the card's text."""
    body = _get(scheduler_url + "/review/next").json()
    card = body["card"]
    assert card is not None, "the scheduler should have pulled new sentences from content"
    if card["card_type"] == "sentence":
        direct = _get(f"{content_url}/sentences/{body['content']['sentence']['id']}").json()
    else:
        direct = _get(f"{content_url}/words/{body['content']['word']['id']}").json()
    assert body["content"] == direct                     # passed through unchanged
    assert set(body["intervals"]) == {"0", "3", "4", "5"}


def test_rating_a_card_is_saved_by_the_scheduler(scheduler_url):
    card_id = _get(scheduler_url + "/review/next").json()["card"]["id"]
    rated = requests.post(f"{scheduler_url}/review/{card_id}", json={"quality": 4}, timeout=TIMEOUT)
    assert rated.status_code == 200 and rated.json()["interval_days"] >= 1
    assert _get(scheduler_url + "/stats").json()["reviewed_today"] >= 1


def test_quiz_answers_are_scored_by_content_through_the_scheduler(content_url, scheduler_url):
    quiz = _get(content_url + "/placement/quiz").json()
    assert len(quiz["questions"]) == 8
    answers = {question["field"]: "dont-know" for question in quiz["questions"]}
    placed = requests.post(scheduler_url + "/placement", json={"answers": answers}, timeout=TIMEOUT)
    assert placed.status_code == 200
    assert placed.json() == {"level": 0, "level_name": "Starter", "skipped": 0}
    assert _get(scheduler_url + "/stats").json()["level_name"] == "Starter"


def test_a_sentence_added_through_content_is_stored_with_its_words(content_url):
    added = requests.post(content_url + "/sentences", json={"spanish": "Ojalá funcione la integración.",
                                                            "english": "I hope the integration works."},
                          timeout=TIMEOUT)
    assert added.status_code in (201, 400)               # 400 when an earlier run already added it
    if added.status_code == 201:
        detail = _get(f"{content_url}/sentences/{added.json()['id']}").json()
        assert detail["sentence"]["grammar_note"].startswith("Ojalá")
        assert {w["headword"] for w in detail["words"]} >= {"ojalá", "funcione", "integración"}


def test_both_services_allow_only_the_ui_origin(content_url, scheduler_url):
    for base in (content_url, scheduler_url):
        assert _get(base + "/health").headers["Access-Control-Allow-Origin"] == UI_ORIGIN
