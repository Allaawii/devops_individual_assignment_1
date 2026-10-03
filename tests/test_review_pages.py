"""Smoke tests for the dashboard and review pages."""

import pytest

from trainer import create_app
from trainer.config import Config
from trainer.scheduler.algorithms import AGAIN, GOOD


@pytest.fixture
def client(tmp_path):
    return create_app(Config(data_dir=str(tmp_path), new_cards_per_day=15)).test_client()


def _add(client, spanish="El gato come.", english="The cat eats."):
    client.post("/sentences/new", data={"spanish": spanish, "english": english})


def test_empty_dashboard_invites_you_to_add_a_sentence(client):
    page = client.get("/").get_data(as_text=True)
    assert "Due now" in page
    assert "Add a sentence" in page


def test_dashboard_offers_a_review_once_cards_exist(client):
    _add(client)
    page = client.get("/").get_data(as_text=True)
    assert "Start review" in page


def test_with_no_cards_the_review_page_says_done(client):
    page = client.get("/review").get_data(as_text=True)
    assert "Done for today" in page


def test_sentence_card_shows_front_and_answer(client):
    _add(client, "Hay que estudiar.", "One must study.")
    page = client.get("/review").get_data(as_text=True)
    assert "Sentence card" in page
    assert "Hay que estudiar." in page
    assert "One must study." in page            # inside <details>, hidden until clicked
    assert "Hay que + infinitive" in page
    for label in ["Again", "Hard", "Good", "Easy"]:
        assert f">{label}</button>" in page


def test_rating_a_card_moves_on_to_the_next_one(client):
    _add(client)                                  # cards: 1 sentence, 2 gato, 3 come
    response = client.post("/review/1", data={"quality": GOOD})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/review")
    page = client.get("/review").get_data(as_text=True)
    assert "Word card" in page
    assert "gato" in page
    assert "El gato come." in page                # example sentence on the word card


def test_after_every_card_is_rated_the_day_is_done(client):
    _add(client)
    for card_id in (1, 2, 3):
        client.post(f"/review/{card_id}", data={"quality": AGAIN})
    page = client.get("/review").get_data(as_text=True)
    assert "Done for today" in page
    assert "You reviewed 3 cards today" in page


@pytest.mark.parametrize("data", [{}, {"quality": "abc"}, {"quality": "9"}])
def test_invalid_rating_is_400(client, data):
    _add(client)
    assert client.post("/review/1", data=data).status_code == 400


def test_rating_an_unknown_card_is_404(client):
    assert client.post("/review/999", data={"quality": GOOD}).status_code == 404
