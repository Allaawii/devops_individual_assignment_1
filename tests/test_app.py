"""Tests for create_app(): startup checks and the wiring between the two domains."""

from datetime import date

import pytest

from trainer import create_app
from trainer.config import Config
from trainer.scheduler.models import SENTENCE_CARD

TODAY = date(2026, 9, 30)


@pytest.fixture
def app(tmp_path):
    return create_app(Config(data_dir=str(tmp_path)))


def test_unknown_scheduler_stops_the_app_at_startup(tmp_path):
    with pytest.raises(ValueError, match="Unknown SCHEDULER"):
        create_app(Config(data_dir=str(tmp_path), scheduler="sm3"))


def test_health_route(app):
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_adding_a_sentence_creates_its_cards_through_the_observer(app):
    content = app.extensions["content_service"]
    reviews = app.extensions["review_service"]
    with app.app_context():
        content.add_sentence("El gato come.", "The cat eats.")
    with app.app_context():  # a new "request": proves the cards were committed
        assert reviews.stats(TODAY).total_cards == 3  # 1 sentence card + gato + come
        assert reviews.next_card(TODAY).card_type == SENTENCE_CARD


def test_sentence_and_cards_roll_back_together(app):
    content = app.extensions["content_service"]
    reviews = app.extensions["review_service"]
    with pytest.raises(RuntimeError):
        with app.app_context():
            content.add_sentence("El gato come.", "The cat eats.")
            raise RuntimeError("request failed after the sentence was added")
    with app.app_context():
        assert content.count_sentences() == 0
        assert reviews.stats(TODAY).total_cards == 0
