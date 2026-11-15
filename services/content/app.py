"""Content service entry point and composition root.

Startup order: connect to SQL Server (with retries), apply pending migrations, import the seed
if the database is empty, then serve. In the container gunicorn calls create_app(); locally
`python app.py` runs Flask's own server (DATABASE_URL must be set either way).
"""

import logging
import sys
from pathlib import Path

from flask import Flask

from content import db
from content.config import Config
from content.repository import MssqlSentenceRepository, MssqlWordRepository
from content.seed import load_seed_if_empty
from content.service import ContentService
from content.web import create_web_app
from migrate import migrate

log = logging.getLogger("content")


def create_app(config: Config | None = None) -> Flask:
    """Prepare the database, then build the Flask app with the real repositories."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # we log every request ourselves
    config = config or Config.from_env()
    prepare_database(config)
    app = create_web_app(build_service(db.get_db), cors_origin=config.cors_origin, version=config.git_sha,
                         check_db=db.check_health)
    db.init_app(app, config.database_url)
    return app


def prepare_database(config: Config) -> None:
    """Connect with retries, migrate, and seed an empty database: all on one startup connection."""
    conn = db.connect_with_retry(config.database_url, config.db_retry_seconds)
    try:
        migrate(conn, Path(config.migrations_dir))
        added = load_seed_if_empty(build_service(lambda: conn), Path(config.seed_dir))
        conn.commit()  # the whole seed import is one transaction
        if added:
            log.info("seed: imported %d sentences", added)
    finally:
        conn.close()


def build_service(get_conn: db.GetConnection) -> ContentService:
    return ContentService(MssqlSentenceRepository(get_conn), MssqlWordRepository(get_conn))


if __name__ == "__main__":
    settings = Config.from_env()
    create_app(settings).run(host="0.0.0.0", port=settings.port, debug=False)
