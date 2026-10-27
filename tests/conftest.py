import pytest

from app.settings import Settings

APP_ENV_VARS = [
    "APP_ENV",
    "LOG_LEVEL",
    "ANTHROPIC_API_KEY",
    "LLM_MODEL",
    "LLM_CONCURRENCY",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's shell environment from leaking into tests."""
    for name in APP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    # _env_file=None: never read the developer's real .env in tests
    return Settings(_env_file=None, app_env="test", neo4j_password="test-password")
