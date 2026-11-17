"""Scheduler service entry point and composition root.

Startup order: check the SCHEDULER setting, connect to SQL Server (with retries), apply pending
migrations, then serve. The scheduler seeds nothing: its cards come from pulling content.
In the container gunicorn calls create_app(); locally `python app.py` runs Flask's own server.
"""

import logging
import sys
from pathlib import Path

from flask import Flask

from migrate import migrate
from scheduler import db
from scheduler.algorithms import get_strategy
from scheduler.config import Config
from scheduler.content_client import HttpContentClient
from scheduler.repository import MssqlCardRepository, MssqlReviewLog, MssqlSettingsStore
from scheduler.service import ReviewService
from scheduler.web import create_web_app

log = logging.getLogger("scheduler")


def create_app(config: Config | None = None) -> Flask:
    """Prepare the database, then build the Flask app with the real repositories and content client."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # we log every request ourselves
    config = config or Config.from_env()
    strategy = get_strategy(config.scheduler)                # fails fast on an unknown SCHEDULER
    prepare_database(config)

    get_conn = db.get_db
    service = ReviewService(MssqlCardRepository(get_conn), MssqlReviewLog(get_conn), MssqlSettingsStore(get_conn),
                            strategy, config.new_cards_per_day,
                            HttpContentClient(config.content_url, config.content_timeout_s))
    app = create_web_app(service, cors_origin=config.cors_origin, version=config.git_sha, check_db=db.check_health)
    db.init_app(app, config.database_url)
    log.info("scheduler ready: %s, content at %s", config.scheduler, config.content_url)
    return app


def prepare_database(config: Config) -> None:
    """Connect with retries and apply pending migrations on one startup connection."""
    conn = db.connect_with_retry(config.database_url, config.db_retry_seconds)
    try:
        migrate(conn, Path(config.migrations_dir))
    finally:
        conn.close()


if __name__ == "__main__":
    settings = Config.from_env()
    create_app(settings).run(host="0.0.0.0", port=settings.port, debug=False)
