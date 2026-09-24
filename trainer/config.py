"""Environment-driven configuration for the trainer app."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """App settings, read once from environment variables at startup."""

    port: int = 8000
    data_dir: str = "./data"
    scheduler: str = "sm2"
    new_cards_per_day: int = 15

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables, falling back to defaults."""
        return cls(
            port=int(os.environ.get("PORT", 8000)),
            data_dir=os.environ.get("DATA_DIR", "./data"),
            scheduler=os.environ.get("SCHEDULER", "sm2"),
            new_cards_per_day=int(os.environ.get("NEW_CARDS_PER_DAY", 15)),
        )
