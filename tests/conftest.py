import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

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
    "DATA_DIR",
    "RUN_WORKER",
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
        data_dir=tmp_path / "data",
        run_worker=False,
    )


class FakeLLM:
    """Stands in for the chat model. `replies` maps an output schema (or `str` for free text) to a function
    of the prompt that returns the reply; `prompts` records every prompt sent."""

    def __init__(self) -> None:
        self.replies: dict[Any, Callable[[str], Any]] = {}
        self.prompts: list[str] = []

    def with_structured_output(self, schema: type[BaseModel]) -> "_Bound":
        return _Bound(self, schema)

    def invoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        return SimpleNamespace(content=self.replies[str](prompt))


class _Bound:
    def __init__(self, llm: FakeLLM, schema: type[BaseModel]) -> None:
        self.llm, self.schema = llm, schema

    def invoke(self, prompt: str) -> Any:
        self.llm.prompts.append(prompt)
        if self.schema not in self.llm.replies:
            raise AssertionError(f"FakeLLM has no reply for {self.schema.__name__}")
        return self.llm.replies[self.schema](prompt)


@pytest.fixture
def use_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Make every module that called `get_settings()` see the test settings (never the developer's .env)."""
    for name, module in list(sys.modules.items()):
        if name.split(".")[0] in ("app", "core", "workers") and hasattr(module, "get_settings"):
            monkeypatch.setattr(module, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def fake_llm(use_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> FakeLLM:
    from core import llm

    fake = FakeLLM()
    monkeypatch.setattr(llm, "_model", lambda: fake)
    return fake
