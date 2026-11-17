"""The scheduler JSON API. Routes are thin: read the request, call ReviewService, return JSON.

Every error has the same shape: {"error": "<code>", "message": "<text for a person>"}.
ContentUnavailable is not caught here: web.py turns it into the designed 503 for every route.
"""

from datetime import date, datetime
from typing import Any

from flask import Blueprint, jsonify, request

from scheduler.models import NextReview, ReviewStats
from scheduler.service import DAILY_GOAL_ERROR, MAX_DAILY_GOAL, MIN_DAILY_GOAL, ReviewService


def error_response(status: int, code: str, message: str):
    """A JSON error in the shared shape, with its HTTP status."""
    return jsonify(error=code, message=message), status


def create_blueprint(reviews: ReviewService) -> Blueprint:
    """Build the API blueprint around the service it should use."""
    bp = Blueprint("scheduler_api", __name__)

    @bp.get("/stats")
    def stats():
        level = reviews.level()
        return jsonify(**_stats(reviews.stats(date.today())), goal=reviews.daily_goal(),
                       level=level[0] if level else None, level_name=level[1] if level else None)

    @bp.get("/goal")
    def get_goal():
        return jsonify(goal=reviews.daily_goal(), default=reviews.default_new_cards_per_day(),
                       min=MIN_DAILY_GOAL, max=MAX_DAILY_GOAL)

    @bp.put("/goal")
    def set_goal():
        goal = _json_body().get("goal")
        if not _is_int(goal):
            return error_response(400, "invalid_goal", DAILY_GOAL_ERROR)
        try:
            reviews.set_daily_goal(goal)
        except ValueError as error:
            return error_response(400, "invalid_goal", str(error))
        return jsonify(goal=goal)

    @bp.get("/review/next")
    def next_review():
        today = date.today()
        screen = reviews.next_review(today)
        if screen is None:
            return jsonify(card=None, progress=_progress(reviews.stats(today)))
        return jsonify(_review_screen(screen))

    @bp.post("/review/<int:card_id>")
    def rate(card_id: int):
        quality = _json_body().get("quality")
        if not _is_int(quality):
            return error_response(400, "invalid_quality", "Send quality as a whole number from 0 to 5.")
        try:
            state = reviews.review(card_id, quality, datetime.now())
        except LookupError:
            return error_response(404, "not_found", f"There is no card with id {card_id}.")
        except ValueError as error:
            return error_response(400, "invalid_quality", str(error))
        return jsonify(card_id=card_id, interval_days=state.interval_days, due_date=state.due_date.isoformat())

    @bp.post("/placement")
    def placement():
        body = _json_body()
        answers = body.get("answers")
        if body.get("skip") is True:
            answers = None
        elif not isinstance(answers, dict) or not all(isinstance(v, str) for v in answers.values()):
            return error_response(400, "invalid_answers", 'Send {"answers": {field: chosen option}} or {"skip": true}.')
        outcome = reviews.place_learner(answers, date.today())
        return jsonify(level=outcome.level, level_name=outcome.level_name, skipped=outcome.skipped)

    return bp


def _json_body() -> dict[str, Any]:
    """The request's JSON object, or an empty dict if the body is missing, invalid or not an object."""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _is_int(value: Any) -> bool:
    """True for a JSON whole number. bool is excluded, because Python counts True as 1."""
    return isinstance(value, int) and not isinstance(value, bool)


def _stats(stats: ReviewStats) -> dict[str, int]:
    return {"due_now": stats.due_now, "new_left_today": stats.new_left_today,
            "reviewed_today": stats.reviewed_today, "total_cards": stats.total_cards}


def _progress(stats: ReviewStats) -> dict[str, int]:
    """Reviews done today, and how many are still waiting (due now plus the rest of today's new cards)."""
    return {"done": stats.reviewed_today, "remaining": stats.due_now + stats.new_left_today}


def _review_screen(screen: NextReview) -> dict[str, Any]:
    return {
        "card": {"id": screen.card.id, "card_type": screen.card.card_type},
        "content": screen.content,
        "intervals": {str(quality): days for quality, days in screen.intervals.items()},
        "progress": _progress(screen.stats),
    }
