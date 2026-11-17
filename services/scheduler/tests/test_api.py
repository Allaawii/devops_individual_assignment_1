"""Tests for the scheduler JSON API, through Flask's test client with fakes for storage and content."""

from datetime import date

import pytest

from scheduler.content_client import Placement


def _first_card(client, content) -> int:
    content.sentences = {1: [10]}
    return client.get("/review/next").get_json()["card"]["id"]


# ----- stats and goal -----

def test_stats_before_anything_happened(client):
    assert client.get("/stats").get_json() == {"due_now": 0, "new_left_today": 15, "reviewed_today": 0,
                                               "total_cards": 0, "goal": None, "level": None, "level_name": None}


def test_stats_still_answer_while_content_is_down(client, content):
    content.down = True
    assert client.get("/stats").status_code == 200


def test_goal_can_be_read_and_set(client):
    assert client.get("/goal").get_json() == {"goal": None, "default": 15, "min": 1, "max": 100}
    assert client.put("/goal", json={"goal": 20}).get_json() == {"goal": 20}
    assert client.get("/goal").get_json()["goal"] == 20
    assert client.get("/stats").get_json()["new_left_today"] == 20


@pytest.mark.parametrize("body", [{}, {"goal": "20"}, {"goal": True}, {"goal": 2.5}, {"goal": 0}, {"goal": 101}])
def test_bad_goal_is_a_400(client, body):
    response = client.put("/goal", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_goal"


# ----- review -----

def test_next_review_has_the_card_its_text_intervals_and_progress(client, content):
    content.sentences = {1: [10]}
    body = client.get("/review/next").get_json()
    assert body["card"] == {"id": 1, "card_type": "sentence"}
    assert body["content"]["sentence"]["id"] == 1
    assert body["intervals"] == {"0": 1, "3": 1, "4": 1, "5": 1}
    assert body["progress"] == {"done": 0, "remaining": 15}


def test_nothing_left_gives_a_null_card_with_progress(client):
    assert client.get("/review/next").get_json() == {"card": None, "progress": {"done": 0, "remaining": 15}}


def test_next_review_while_content_is_down_is_the_designed_503(client, content):
    content.down = True
    response = client.get("/review/next")
    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "content_unavailable"
    assert "progress is safe" in body["message"]


def test_rating_a_card_returns_its_new_schedule(client, content):
    card_id = _first_card(client, content)
    body = client.post(f"/review/{card_id}", json={"quality": 4}).get_json()
    assert body["card_id"] == card_id and body["interval_days"] == 1
    assert date.fromisoformat(body["due_date"]) > date.today()
    assert client.get("/stats").get_json()["reviewed_today"] == 1


@pytest.mark.parametrize("body", [{}, {"quality": "4"}, {"quality": 9}, {"quality": False}])
def test_bad_quality_is_a_400(client, content, body):
    card_id = _first_card(client, content)
    response = client.post(f"/review/{card_id}", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_quality"


def test_rating_an_unknown_card_is_a_404(client):
    response = client.post("/review/99", json={"quality": 4})
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


# ----- placement -----

def test_placement_scores_through_content_and_stores_the_level(client, content):
    content.placement = Placement(1, "Beginner", [1, 2], [10])
    body = client.post("/placement", json={"answers": {"q1": "a"}}).get_json()
    assert body == {"level": 1, "level_name": "Beginner", "skipped": 3}
    stats = client.get("/stats").get_json()
    assert (stats["level"], stats["level_name"], stats["total_cards"]) == (1, "Beginner", 3)


def test_skipping_placement_works_while_content_is_down(client, content):
    content.down = True
    assert client.post("/placement", json={"skip": True}).get_json() == {"level": 0, "level_name": "Starter",
                                                                         "skipped": 0}


def test_placement_while_content_is_down_is_the_designed_503(client, content):
    content.down = True
    response = client.post("/placement", json={"answers": {"q1": "a"}})
    assert response.status_code == 503
    assert response.get_json()["error"] == "content_unavailable"


@pytest.mark.parametrize("body", [{}, {"answers": "a"}, {"answers": {"q1": 1}}, {"skip": "yes"}])
def test_bad_placement_body_is_a_400(client, body):
    response = client.post("/placement", json=body)
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_answers"
