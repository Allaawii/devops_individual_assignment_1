"""Environment-driven configuration for the trainer app."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """App settings, read once from environment variables at startup. The defaults are written once, here."""

    port: int = 8000
    data_dir: str = "./data"
    scheduler: str = "sm2"
    new_cards_per_day: int = 15

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables; anything unset keeps the default above."""
        return cls(
            port=int(os.environ.get("PORT", cls.port)),
            data_dir=os.environ.get("DATA_DIR", cls.data_dir),
            scheduler=os.environ.get("SCHEDULER", cls.scheduler),
            new_cards_per_day=int(os.environ.get("NEW_CARDS_PER_DAY", cls.new_cards_per_day)),
        )
