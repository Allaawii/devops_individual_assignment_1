"""Environment-driven configuration for the scheduler service."""

import os
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR = str(Path(__file__).parent.parent / "migrations")


@dataclass
class Config:
    """Settings read once from environment variables at startup. The defaults are written once, here."""

    database_url: str = ""             # secret: mssql://user:password@host:1433/database
    port: int = 8000
    cors_origin: str = "http://localhost:8080"
    git_sha: str = "dev"
    db_retry_seconds: int = 90         # how long startup keeps trying to reach the database
    content_url: str = "http://content:8000"
    content_timeout_s: float = 2.0     # longest wait for one call to the content service
    scheduler: str = "sm2"             # scheduling algorithm: sm2 or leitner
    new_cards_per_day: int = 15        # default daily goal until the learner picks one
    migrations_dir: str = MIGRATIONS_DIR

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables. DATABASE_URL is required; the rest have defaults."""
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set (format: mssql://user:password@host:1433/database)")
        return cls(
            database_url=database_url,
            port=int(os.environ.get("PORT", cls.port)),
            cors_origin=os.environ.get("CORS_ORIGIN", cls.cors_origin),
            git_sha=os.environ.get("GIT_SHA", cls.git_sha),
            db_retry_seconds=int(os.environ.get("DB_RETRY_SECONDS", cls.db_retry_seconds)),
            content_url=os.environ.get("CONTENT_URL", cls.content_url).rstrip("/"),
            content_timeout_s=float(os.environ.get("CONTENT_TIMEOUT_S", cls.content_timeout_s)),
            scheduler=os.environ.get("SCHEDULER", cls.scheduler),
            new_cards_per_day=int(os.environ.get("NEW_CARDS_PER_DAY", cls.new_cards_per_day)),
        )
