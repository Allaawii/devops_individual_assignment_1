"""The Flask app around the API: /health, CORS, one log line per request and JSON errors.

It takes the service and a database check as arguments, so tests can build it with fakes
and no database. app.py builds it with the real repositories.
"""

import logging
import time
from collections.abc import Callable

from flask import Flask, g, request
from werkzeug.exceptions import HTTPException, InternalServerError

from content.api import create_blueprint, error_response
from content.service import ContentService

log = logging.getLogger("content")

ALLOWED_METHODS = "GET, POST, PUT, OPTIONS"


def create_web_app(service: ContentService, *, cors_origin: str, version: str,
                   check_db: Callable[[], None]) -> Flask:
    """Build the Flask app. `check_db` raises if the database cannot be read and written."""
    app = Flask(__name__)
    _add_request_log(app)    # registered first, so the timer also covers the CORS preflight
    _add_cors(app, cors_origin)
    _add_json_errors(app)
    app.register_blueprint(create_blueprint(service))

    @app.get("/health")
    def health():
        try:
            check_db()
        except Exception as error:  # any failure means "not healthy"; the reason goes to the log
            log.warning("health check failed: %s", type(error).__name__)
            return {"status": "error", "db": "error", "version": version}, 503
        return {"status": "ok", "db": "ok", "version": version}

    return app


def _add_request_log(app: Flask) -> None:
    """Log `METHOD PATH STATUS DURATIONms` for every request (the path has no query string)."""

    @app.before_request
    def start_timer():
        g.started = time.perf_counter()

    @app.after_request
    def log_request(response):
        duration_ms = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
        log.info("%s %s %s %dms", request.method, request.path, response.status_code, round(duration_ms))
        return response


def _add_cors(app: Flask, origin: str) -> None:
    """Let the UI's origin, and only that origin, call the API from the browser.

    Browsers send an OPTIONS "preflight" before a PUT or a JSON POST; it is answered with 204.
    """

    @app.before_request
    def preflight():
        if request.method == "OPTIONS":
            return "", 204
        return None

    @app.after_request
    def add_headers(response):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response


def _add_json_errors(app: Flask) -> None:
    """Answer unknown paths, wrong methods and crashes with JSON instead of Flask's HTML pages.

    There is deliberately no handler for Exception itself: a crash must still reach the request
    teardown as an error, so the transaction is rolled back. Flask logs it and then calls the
    InternalServerError handler below.
    """

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        code = (error.name or "error").lower().replace(" ", "_")
        return error_response(error.code or 500, code, error.description or "")

    @app.errorhandler(InternalServerError)
    def crash(error: InternalServerError):
        return error_response(500, "internal_error", "Something went wrong on our side. Please try again.")
