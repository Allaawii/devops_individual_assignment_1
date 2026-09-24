"""Composition root: builds the Flask app."""

from flask import Flask, jsonify

from trainer.config import Config


def create_app(config: Config | None = None) -> Flask:
    """Build and return the Flask app. Wires nothing beyond config for now."""
    app = Flask(__name__)
    app.config["APP_CONFIG"] = config or Config.from_env()

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app
