"""Environment-driven configuration for the content service."""

import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_DIR = Path(__file__).parent.parent
BUNDLED_SEED_DIR = str(SERVICE_DIR / "seed")
MIGRATIONS_DIR = str(SERVICE_DIR / "migrations")


@dataclass
class Config:
    """Settings read once from environment variables at startup. The defaults are written once, here."""

    database_url: str = ""             # secret: mssql://user:password@host:1433/database
    port: int = 8000
    cors_origin: str = "http://localhost:8080"
    git_sha: str = "dev"
    db_retry_seconds: int = 90         # how long startup keeps trying to reach the database
    seed_dir: str = BUNDLED_SEED_DIR   # not an env var; tests point it at a small seed
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
        )
