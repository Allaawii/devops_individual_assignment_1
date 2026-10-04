"""Smoke tests for the daily goal, dashboard and review pages."""

import pytest

from trainer import create_app
from trainer.config import Config
from trainer.scheduler.algorithms import AGAIN, GOOD


@pytest.fixture
def new_client(tmp_path):
    """A first-time learner who hasn't chosen a daily goal yet."""
    return create_app(Config(data_dir=str(tmp_path))).test_client()


@pytest.fixture
def client(new_client):
    """A learner who has already chosen 15 new cards a day."""
    new_client.post("/goal", data={"goal": "15"})
    return new_client


def _add(client, spanish="El gato come.", english="The cat eats."):
    client.post("/sentences/new", data={"spanish": spanish, "english": english})


# ----- daily goal (first start) -----

def test_first_visit_asks_for_a_daily_goal(new_client):
    response = new_client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/goal")
    page = new_client.get("/goal").get_data(as_text=True)
    assert "Welcome" in page
    assert "How much do you want to learn each day?" in page


def test_choosing_a_preset_goal_opens_the_dashboard(new_client):
    response = new_client.post("/goal", data={"goal": "20"})
    assert response.headers["Location"].endswith("/")
    assert "Daily goal: 20 new cards a day" in new_client.get("/").get_data(as_text=True)


def test_custom_number_wins_over_the_preset(new_client):
    new_client.post("/goal", data={"goal": "10", "custom": "7"})
    assert "Daily goal: 7 new cards a day" in new_client.get("/").get_data(as_text=True)


@pytest.mark.parametrize("data", [{}, {"goal": "0"}, {"goal": "500"}, {"custom": "abc"}])
def test_invalid_goal_shows_an_error(new_client, data):
    response = new_client.post("/goal", data=data)
    assert response.status_code == 400
    assert "Choose a goal between 1 and 100" in response.get_data(as_text=True)


def test_goal_can_be_changed_later(client):
    page = client.get("/goal").get_data(as_text=True)
    assert "Daily goal" in page and "Welcome" not in page
    client.post("/goal", data={"goal": "5"})
    assert "Daily goal: 5 new cards a day" in client.get("/").get_data(as_text=True)


def test_goal_limits_the_new_cards_shown(new_client):
    new_client.post("/goal", data={"custom": "1"})
    _add(new_client)                              # 3 cards
    new_client.post("/review/1", data={"quality": GOOD})
    assert "Done for today" in new_client.get("/review").get_data(as_text=True)


# ----- dashboard -----

def test_empty_dashboard_invites_you_to_add_a_sentence(client):
    page = client.get("/").get_data(as_text=True)
    assert "Due now" in page
    assert "Add a sentence" in page


def test_dashboard_offers_a_review_once_cards_exist(client):
    _add(client)
    assert "Start review" in client.get("/").get_data(as_text=True)


# ----- review -----

def test_with_no_cards_the_review_page_says_done(client):
    assert "Done for today" in client.get("/review").get_data(as_text=True)


def test_sentence_card_shows_front_and_answer(client):
    _add(client, "Hay que estudiar.", "One must study.")
    page = client.get("/review").get_data(as_text=True)
    assert "Sentence card" in page
    assert "Hay que estudiar." in page
    assert "One must study." in page            # inside <details>, hidden until clicked
    assert "Hay que + infinitive" in page
    for label in ["Again", "Hard", "Good", "Easy"]:
        assert f">{label}</button>" in page      # plain labels, no times on the buttons


def test_info_box_explains_when_each_card_comes_back(client):
    _add(client)
    page = client.get("/review").get_data(as_text=True)
    assert "What the buttons do" in page
    assert "<strong>Hard</strong>: I remembered it with effort. You'll see this card again" in page
    assert page.count("tomorrow.") == 4          # SM-2: a new card comes back tomorrow for every rating


def test_rating_buttons_have_keyboard_shortcuts(client):
    _add(client)
    page = client.get("/review").get_data(as_text=True)
    for key in "1234":
        assert f'accesskey="{key}"' in page


def test_review_page_shows_todays_progress(client):
    _add(client)                                  # 3 cards
    client.post("/review/1", data={"quality": GOOD})
    page = client.get("/review").get_data(as_text=True)
    assert '<progress value="1" max="3"' in page
    assert "1 done · 2 to go" in page


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
