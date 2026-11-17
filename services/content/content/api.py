"""The content JSON API. Routes are thin: read the request, call ContentService, return JSON.

Every error has the same shape: {"error": "<code>", "message": "<text for a person>"}.
"""

from dataclasses import asdict
from typing import Any

from flask import Blueprint, jsonify, request

from content.models import Sentence, SentenceDetail, Word
from content.placement import LEVELS
from content.service import ContentService

DEFAULT_FEED_LIMIT = 20


def error_response(status: int, code: str, message: str):
    """A JSON error in the shared shape, with its HTTP status."""
    return jsonify(error=code, message=message), status


def create_blueprint(content: ContentService) -> Blueprint:
    """Build the API blueprint around the service it should use."""
    bp = Blueprint("content_api", __name__)

    @bp.get("/sentences")
    def list_sentences():
        page = content.list_sentences(_int_arg("page", 1))
        return jsonify(items=[_sentence(s) for s in page.items], page=page.number, has_next=page.has_next,
                       total=content.count_sentences())

    @bp.post("/sentences")
    def create_sentence():
        body = _json_body()
        spanish, english, note = body.get("spanish"), body.get("english"), body.get("grammar_note")
        if not isinstance(spanish, str) or not isinstance(english, str) or not isinstance(note, (str, type(None))):
            return error_response(400, "invalid_sentence", "Send spanish and english as text (grammar_note optional).")
        try:
            sentence = content.add_sentence(spanish, english, note)
        except ValueError as error:
            return error_response(400, "invalid_sentence", str(error))
        return jsonify(_sentence(sentence)), 201

    @bp.get("/sentences/<int:sentence_id>")
    def get_sentence(sentence_id: int):
        detail = content.get_sentence(sentence_id)
        if detail is None:
            return _not_found("sentence", sentence_id)
        return jsonify(_sentence_detail(detail))

    @bp.get("/sentences/feed")
    def feed():
        items = content.feed(_int_arg("after_id", 0), _int_arg("limit", DEFAULT_FEED_LIMIT))
        return jsonify(items=[asdict(item) for item in items])

    @bp.get("/words")
    def list_words():
        page = content.list_words(_int_arg("page", 1))
        return jsonify(items=[_word(w) for w in page.items], page=page.number, has_next=page.has_next)

    @bp.get("/words/<int:word_id>")
    def get_word(word_id: int):
        word = content.get_word(word_id)
        if word is None:
            return _not_found("word", word_id)
        return jsonify(word=_word(word), examples=[_sentence(s) for s in content.example_sentences(word_id)])

    @bp.put("/words/<int:word_id>/meaning")
    def set_meaning(word_id: int):
        meaning = _json_body().get("meaning")
        if not isinstance(meaning, (str, type(None))):
            return error_response(400, "invalid_meaning", "Send meaning as text, or null to clear it.")
        try:
            word = content.set_meaning(word_id, meaning)
        except ValueError as error:
            return error_response(400, "invalid_meaning", str(error))
        if word is None:
            return _not_found("word", word_id)
        return jsonify(_word(word))

    @bp.get("/placement/quiz")
    def placement_quiz():
        questions = [{"field": q.field, "spanish": q.spanish, "options": q.options, "level": q.level}
                     for q in content.placement_quiz()]   # the right answer is never sent
        return jsonify(questions=questions, levels=list(LEVELS))

    @bp.post("/placement/score")
    def placement_score():
        answers = _json_body().get("answers")
        if not isinstance(answers, dict) or not all(isinstance(v, str) for v in answers.values()):
            return error_response(400, "invalid_answers", "Send answers as an object of field: chosen option.")
        return jsonify(asdict(content.score_placement(answers)))

    return bp


def _int_arg(name: str, default: int) -> int:
    """An integer query parameter; a missing or non-numeric value gives the default."""
    return request.args.get(name, default, type=int)


def _json_body() -> dict[str, Any]:
    """The request's JSON object, or an empty dict if the body is missing, invalid or not an object."""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _not_found(kind: str, item_id: int):
    return error_response(404, "not_found", f"There is no {kind} with id {item_id}.")


def _sentence(sentence: Sentence) -> dict[str, Any]:
    return asdict(sentence)


def _word(word: Word) -> dict[str, Any]:
    return asdict(word)


def _sentence_detail(detail: SentenceDetail) -> dict[str, Any]:
    return {"sentence": _sentence(detail.sentence), "words": [_word(w) for w in detail.words],
            "key_words": [_word(w) for w in detail.key_words()]}
