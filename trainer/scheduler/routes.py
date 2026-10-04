"""Dashboard, daily goal, placement quiz and review pages.

These are the only routes that use both domains (allowed by ADR-2): ReviewService picks the
card by ID, then ContentService supplies the text to show. After a split this becomes one HTTP call.
"""

from datetime import date, datetime

from flask import Blueprint, abort, redirect, render_template, request, url_for

from trainer.content.placement import DONT_KNOW, LEVELS
from trainer.content.service import ContentService
from trainer.scheduler.algorithms import AGAIN, EASY, GOOD, HARD
from trainer.scheduler.models import SENTENCE_CARD, Card
from trainer.scheduler.service import DAILY_GOAL_ERROR, MAX_DAILY_GOAL, MIN_DAILY_GOAL, ReviewService

# (button label, quality score, what pressing it means)
RATINGS = [
    ("Again", AGAIN, "I forgot it"),
    ("Hard", HARD, "I remembered it with effort"),
    ("Good", GOOD, "I remembered it"),
    ("Easy", EASY, "It was too easy"),
]
# (new cards a day, name shown on the goal page)
GOAL_PRESETS = [(5, "Light"), (10, "Steady"), (20, "Serious"), (30, "Intense")]


def create_blueprint(reviews: ReviewService, content: ContentService) -> Blueprint:
    """Build the 'review' blueprint around the two services it needs."""
    bp = Blueprint("review", __name__)

    @bp.get("/")
    def dashboard():
        if reviews.daily_goal() is None:
            return redirect(url_for("review.goal"))
        return render_template("index.html", stats=reviews.stats(date.today()), goal=reviews.new_cards_per_day(),
                               sentence_count=content.count_sentences(), level=_level_name(reviews.level()))

    @bp.get("/goal")
    def goal():
        return _goal_page(reviews)

    @bp.post("/goal")
    def save_goal():
        chosen = request.form.get("custom") or request.form.get("goal")
        try:
            reviews.set_daily_goal(int(chosen))
        except (TypeError, ValueError):  # missing, not a number, or outside the allowed range
            return _goal_page(reviews, DAILY_GOAL_ERROR), 400
        # A new learner goes on to the level quiz; someone changing their goal goes back home.
        return redirect(url_for("review.placement" if reviews.level() is None else "review.dashboard"))

    @bp.get("/placement")
    def placement():
        return render_template("review/placement.html", quiz=content.placement_quiz(), dont_know=DONT_KNOW)

    @bp.post("/placement")
    def submit_placement():
        level = 0 if "skip" in request.form else content.placement_level(request.form)
        skipped = reviews.place_learner(level, *content.known_material(level), date.today())
        return render_template("review/placement_result.html", level=level, levels=LEVELS, skipped=skipped)

    @bp.get("/review")
    def show_card():
        today = date.today()
        card = reviews.next_card(today)
        if card is None:
            return render_template("review/done.html", stats=reviews.stats(today))
        return render_template("review/card.html", card=card, ratings=RATINGS,
                               intervals=reviews.preview_intervals(card, today),
                               stats=reviews.stats(today), **_card_content(card, content))

    @bp.post("/review/<int:card_id>")
    def rate(card_id: int):
        quality = request.form.get("quality", type=int)
        if quality is None:
            abort(400)
        try:
            reviews.review(card_id, quality, datetime.now())
        except LookupError:
            abort(404)
        except ValueError:
            abort(400)
        return redirect(url_for("review.show_card"))

    return bp


def _goal_page(reviews: ReviewService, error: str | None = None) -> str:
    return render_template("review/goal.html", presets=GOAL_PRESETS, error=error,
                           first_time=reviews.daily_goal() is None, current=reviews.new_cards_per_day(),
                           min_goal=MIN_DAILY_GOAL, max_goal=MAX_DAILY_GOAL)


def _level_name(level: int | None) -> str | None:
    return LEVELS[level] if level is not None else None


def _card_content(card: Card, content: ContentService) -> dict:
    """The text for a card's two faces, fetched from the content domain by ID."""
    if card.card_type == SENTENCE_CARD:
        detail = content.get_sentence(card.sentence_id)
        return {"sentence": detail.sentence, "key_words": detail.key_words()}
    return {"word": content.get_word(card.word_id), "examples": content.example_sentences(card.word_id)}
