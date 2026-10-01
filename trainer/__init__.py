"""Composition root: the only place that knows about both domains and wires them together."""

from flask import Flask, jsonify

from trainer import db
from trainer.config import Config
from trainer.content.repository import SqliteSentenceRepository, SqliteWordRepository
from trainer.content.service import ContentService
from trainer.scheduler.algorithms import get_strategy
from trainer.scheduler.repository import SqliteCardRepository, SqliteReviewLog
from trainer.scheduler.service import ReviewService


def create_app(config: Config | None = None) -> Flask:
    """Build the app: config, database, both services, and the observer link between them."""
    app = Flask(__name__)
    config = config or Config.from_env()
    app.config["APP_CONFIG"] = config
    strategy = get_strategy(config.scheduler)  # fails fast on an unknown SCHEDULER
    db.init_app(app, config.data_dir)

    content_service = ContentService(SqliteSentenceRepository(db.get_db), SqliteWordRepository(db.get_db))
    review_service = ReviewService(SqliteCardRepository(db.get_db), SqliteReviewLog(db.get_db),
                                   strategy, config.new_cards_per_day)
    content_service.subscribe(review_service.on_sentence_added)
    app.extensions["content_service"] = content_service
    app.extensions["review_service"] = review_service

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app
