from pathlib import Path

import pytest

from app.settings import Settings

APP_ENV_VARS = [
    "APP_ENV",
    "LOG_LEVEL",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "LLM_CONCURRENCY",
    "OLLAMA_BASE_URL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "SQLITE_PATH",
]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's shell environment from leaking into tests."""
    for name in APP_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # _env_file=None: never read the developer's real .env in tests
    return Settings(
        _env_file=None,
        app_env="test",
        neo4j_password="test-password",
        sqlite_path=tmp_path / "app.db",
        cache_dir=tmp_path / "cache",
    )
