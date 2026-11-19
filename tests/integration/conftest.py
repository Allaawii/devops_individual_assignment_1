"""Where the running services are. The defaults are the ports docker-compose.yml publishes."""

import os

import pytest

UI_ORIGIN = "http://localhost:8080"


@pytest.fixture(scope="session")
def content_url() -> str:
    return os.environ.get("CONTENT_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def scheduler_url() -> str:
    return os.environ.get("SCHEDULER_URL", "http://localhost:8002")
