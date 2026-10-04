"""Smoke tests for the daily goal, dashboard and review pages.

`client` (from conftest.py) is a first-time visitor; `learner` has already chosen a daily goal.
"""

import pytest

from trainer import create_app
from trainer.config import Config
from trainer.scheduler.algorithms import AGAIN, GOOD


@pytest.fixture
def learner(client):
    """A learner who has already chosen 15 new cards a day."""
    client.post("/goal", data={"goal": "15"})
    return client


# ----- daily goal (first start) -----

def test_first_visit_asks_for_a_daily_goal(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/goal")
    page = client.get("/goal").get_data(as_text=True)
    assert "Welcome" in page
    assert "How much do you want to learn each day?" in page


def test_first_goal_leads_to_the_level_quiz(client):
    response = client.post("/goal", data={"goal": "20"})
    assert response.headers["Location"].endswith("/placement")
    assert "Daily goal: 20 new cards a day" in client.get("/").get_data(as_text=True)


def test_custom_number_wins_over_the_preset(client):
    client.post("/goal", data={"goal": "10", "custom": "7"})
    assert "Daily goal: 7 new cards a day" in client.get("/").get_data(as_text=True)


@pytest.mark.parametrize("data", [{}, {"goal": "0"}, {"goal": "500"}, {"custom": "abc"}])
def test_invalid_goal_shows_an_error(client, data):
    response = client.post("/goal", data=data)
    assert response.status_code == 400
    assert "Choose a goal between 1 and 100" in response.get_data(as_text=True)


def test_goal_can_be_changed_later(learner):
    learner.post("/placement", data={"skip": "1"})
    page = learner.get("/goal").get_data(as_text=True)
    assert "Daily goal" in page and "Welcome" not in page
    response = learner.post("/goal", data={"goal": "5"})
    assert response.headers["Location"].endswith("/")     # placed already, so straight home
    assert "Daily goal: 5 new cards a day" in learner.get("/").get_data(as_text=True)


def test_goal_limits_the_new_cards_shown(client, add_sentence):
    client.post("/goal", data={"custom": "1"})
    add_sentence()                                # 3 cards
    client.post("/review/1", data={"quality": GOOD})
    assert "Done for today" in client.get("/review").get_data(as_text=True)


# ----- dashboard -----

def test_empty_dashboard_invites_you_to_add_a_sentence(learner):
    page = learner.get("/").get_data(as_text=True)
    assert "Due now" in page
    assert "Add a sentence" in page


def test_dashboard_offers_a_review_once_cards_exist(learner, add_sentence):
    add_sentence()
    assert "Start review" in learner.get("/").get_data(as_text=True)


# ----- review -----

def test_with_no_cards_the_review_page_says_done(learner):
    assert "Done for today" in learner.get("/review").get_data(as_text=True)


def test_sentence_card_shows_front_and_answer(learner, add_sentence):
    add_sentence("Hay que estudiar.", "One must study.")
    page = learner.get("/review").get_data(as_text=True)
    assert "Sentence card" in page
    assert "Hay que estudiar." in page
    assert "One must study." in page            # inside <details>, hidden until clicked
    assert "Hay que + infinitive" in page
    for label in ["Again", "Hard", "Good", "Easy"]:
        assert f">{label}</button>" in page      # plain labels, no times on the buttons


def test_sentence_card_shows_its_key_words_instead_of_a_link_away(learner, add_sentence):
    add_sentence("Hay que estudiar.", "One must study.")
    page = learner.get("/review").get_data(as_text=True)
    assert "Key words" in page
    assert '<span lang="es">estudiar</span>' in page
    assert "See the words in this sentence" not in page


def test_info_box_explains_when_each_card_comes_back(learner, add_sentence):
    add_sentence()
    page = learner.get("/review").get_data(as_text=True)
    assert "What the buttons do" in page
    assert "<strong>Hard</strong>: I remembered it with effort. You'll see this card again" in page
    assert page.count("tomorrow.") == 4          # SM-2: a new card comes back tomorrow for every rating


def test_rating_buttons_have_keyboard_shortcuts(learner, add_sentence):
    add_sentence()
    page = learner.get("/review").get_data(as_text=True)
    for key in "1234":
        assert f'accesskey="{key}"' in page


def test_review_page_shows_todays_progress(learner, add_sentence):
    add_sentence()                                # 3 cards
    learner.post("/review/1", data={"quality": GOOD})
    page = learner.get("/review").get_data(as_text=True)
    assert '<progress value="1" max="3"' in page
    assert "1 done · 2 to go" in page


def test_rating_a_card_moves_on_to_the_next_one(learner, add_sentence):
    add_sentence()                                # cards: 1 sentence, 2 gato, 3 come
    response = learner.post("/review/1", data={"quality": GOOD})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/review")
    page = learner.get("/review").get_data(as_text=True)
    assert "Word card" in page
    assert "gato" in page
    assert "El gato come." in page                # example sentence on the word card


def test_after_every_card_is_rated_the_day_is_done(learner, add_sentence):
    add_sentence()
    for card_id in (1, 2, 3):
        learner.post(f"/review/{card_id}", data={"quality": AGAIN})
    page = learner.get("/review").get_data(as_text=True)
    assert "Done for today" in page
    assert "You reviewed 3 cards today" in page


@pytest.mark.parametrize("data", [{}, {"quality": "abc"}, {"quality": "9"}])
def test_invalid_rating_is_400(learner, add_sentence, data):
    add_sentence()
    assert learner.post("/review/1", data=data).status_code == 400


def test_rating_an_unknown_card_is_404(learner):
    assert learner.post("/review/999", data={"quality": GOOD}).status_code == 404


# ----- placement quiz -----

@pytest.fixture
def seeded_app(tmp_path):
    """An app whose seed has 50 sentences, enough for a full quiz (bands of 10)."""
    seed = tmp_path / "seed"
    seed.mkdir()
    rows = "".join(f"Frase número {i}.\tSentence {i}.\ttatoeba\n" for i in range(1, 51))
    (seed / "sentences.tsv").write_text(rows, encoding="utf-8")
    return create_app(Config(data_dir=str(tmp_path / "data"), seed_dir=str(seed)))


@pytest.fixture
def newcomer(seeded_app):
    """A learner on the seeded app who has chosen a goal but not taken the quiz."""
    client = seeded_app.test_client()
    client.post("/goal", data={"goal": "15"})
    return client


def _right_answers(app) -> dict[str, str]:
    with app.app_context():
        return {q.field: q.answer for q in app.extensions["content_service"].placement_quiz()}


def test_dashboard_offers_the_quiz_until_the_learner_is_placed(learner):
    assert "Find my level" in learner.get("/").get_data(as_text=True)
    learner.post("/placement", data={"skip": "1"})
    page = learner.get("/").get_data(as_text=True)
    assert "Find my level" not in page
    assert "Level: Starter" in page


def test_without_a_seed_the_quiz_page_lets_you_continue(learner):
    page = learner.get("/placement").get_data(as_text=True)
    assert "aren't enough built-in sentences" in page
    assert "Continue" in page


def test_quiz_page_shows_eight_questions(newcomer):
    page = newcomer.get("/placement").get_data(as_text=True)
    assert page.count('<fieldset class="panel question">') == 8
    assert page.count(">I'm not sure</label>") == 8


def test_all_answers_right_places_you_at_the_top_and_skips_easy_cards(seeded_app, newcomer):
    page = newcomer.post("/placement", data=_right_answers(seeded_app)).get_data(as_text=True)
    assert "<h1>Advanced</h1>" in page
    assert "<strong>42 cards</strong> were marked as known" in page   # 40 sentences + frase, número
    assert "Level: Advanced" in newcomer.get("/").get_data(as_text=True)
    card_page = newcomer.get("/review").get_data(as_text=True)
    assert "Frase número 41." in card_page          # first sentence of the hardest band


def test_no_right_answers_places_you_as_a_starter(newcomer):
    page = newcomer.post("/placement", data={}).get_data(as_text=True)
    assert "<h1>Starter</h1>" in page
    assert "start from the beginning" in page
    assert "Frase número 1." in newcomer.get("/review").get_data(as_text=True)
