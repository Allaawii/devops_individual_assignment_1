"""Composition root: builds the Flask app."""

from flask import Flask, jsonify

from trainer import db
from trainer.config import Config


def create_app(config: Config | None = None) -> Flask:
    """Build and return the Flask app: config, then the database."""
    app = Flask(__name__)
    config = config or Config.from_env()
    app.config["APP_CONFIG"] = config
    db.init_app(app, config.data_dir)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app
