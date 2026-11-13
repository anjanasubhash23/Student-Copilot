from typing import Any

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from app.settings import Settings
from core import llm


class Answer(BaseModel):
    value: int


def _settings(base: Settings, **overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**base.model_dump(), **overrides})


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"llm_provider": "ollama"}, ChatOllama),
        ({"llm_provider": "anthropic", "llm_model": "claude-x", "anthropic_api_key": "sk-ant-test"}, ChatAnthropic),
        ({"llm_provider": "openai", "llm_model": "gpt-x", "openai_api_key": "sk-test"}, ChatOpenAI),
        ({"llm_provider": "openai", "llm_model": "local", "openai_base_url": "http://localhost:1234/v1"}, ChatOpenAI),
    ],
)
def test_chat_model_matches_provider(settings: Settings, overrides: dict[str, str], expected: type) -> None:
    # Constructing a model makes no network call, so this needs neither Ollama nor an API key.
    model = llm.chat_model(_settings(settings, **overrides))
    assert isinstance(model, expected)


class StubModel:
    """Stands in for a chat model: returns `reply` from with_structured_output(...).invoke()."""

    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.calls = 0

    def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> "StubModel":
        return self

    def invoke(self, prompt: str) -> Any:
        self.calls += 1
        return self.reply


@pytest.fixture
def stub(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> StubModel:
    model = StubModel(Answer(value=42))
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_model", lambda: model)
    return model


def test_structured_returns_validated_object_and_caches(stub: StubModel) -> None:
    assert llm.structured("q", Answer) == Answer(value=42)
    assert llm.structured("q", Answer) == Answer(value=42)
    assert stub.calls == 1  # second call came from the disk cache


def test_structured_validates_dict_replies(stub: StubModel) -> None:
    stub.reply = {"value": "7"}
    assert llm.structured("q", Answer) == Answer(value=7)


def test_cache_is_keyed_by_model(stub: StubModel, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    llm.structured("q", Answer)
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(settings, llm_model="other-model"))
    llm.structured("q", Answer)
    assert stub.calls == 2


def test_prompt_version_changes_with_the_prompt(settings: Settings, tmp_path: Any, monkeypatch: pytest.MonkeyPatch):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    monkeypatch.setattr(llm, "get_settings", lambda: _settings(settings, prompts_dir=prompts))
    (prompts / "x.md").write_text("List the topics.")
    first = llm.prompt_version("x")
    assert len(first) == 8
    assert llm.prompt_version("x") == first
    (prompts / "x.md").write_text("List the topics, briefly.")
    assert llm.prompt_version("x") != first


class _StatusError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def test_unavailable_reason_explains_fixable_llm_errors(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    assert "ollama pull llama3.1:8b" in (
        llm.unavailable_reason(_StatusError("model 'llama3.1:8b' not found", 404)) or ""
    )
    assert "isn't reachable" in (llm.unavailable_reason(httpx.ConnectError("refused")) or "")
    assert "API key was rejected" in (llm.unavailable_reason(_StatusError("unauthorized", 401)) or "")
    assert llm.unavailable_reason(ValueError("bug")) is None


def test_usage_is_tracked_across_threads(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    class Model:
        def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> "Model":
            assert kwargs.get("include_raw") is True
            return self

        def invoke(self, prompt: str) -> Any:
            raw = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 3})
            return {"raw": raw, "parsed": Answer(value=len(prompt)), "parsing_error": None}

    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_model", lambda: Model())
    with llm.track_usage() as usage, ThreadPoolExecutor(2) as pool:
        results = list(llm.map_in_context(pool, lambda p: llm.structured(p, Answer), ["a", "bb", "a"]))
    assert [r.value for r in results] == [1, 2, 1]
    # "a" twice: the second is either a cache hit or, if both ran at once, a second call
    assert usage.calls + usage.cached == 3
    assert usage.input_tokens == 10 * usage.calls and usage.output_tokens == 3 * usage.calls


def test_parsing_error_is_raised(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    class Model:
        def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> "Model":
            return self

        def invoke(self, prompt: str) -> Any:
            return {"raw": None, "parsed": None, "parsing_error": ValueError("bad json")}

    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "_model", lambda: Model())
    with pytest.raises(ValueError, match="bad json"):
        llm.structured("q", Answer)
