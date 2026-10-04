"""Environment-driven configuration for the trainer app."""

import os
from dataclasses import dataclass
from pathlib import Path

BUNDLED_SEED_DIR = str(Path(__file__).parent / "content" / "seed")


@dataclass
class Config:
    """App settings, read once from environment variables at startup. The defaults are written once, here."""

    port: int = 8000
    data_dir: str = "./data"
    scheduler: str = "sm2"
    new_cards_per_day: int = 15
    seed_dir: str = BUNDLED_SEED_DIR  # not an env var; tests point it at an empty folder

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables; anything unset keeps the default above."""
        return cls(
            port=int(os.environ.get("PORT", cls.port)),
            data_dir=os.environ.get("DATA_DIR", cls.data_dir),
            scheduler=os.environ.get("SCHEDULER", cls.scheduler),
            new_cards_per_day=int(os.environ.get("NEW_CARDS_PER_DAY", cls.new_cards_per_day)),
        )
