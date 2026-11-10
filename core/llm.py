"""LLM calls that return validated pydantic objects, cached on disk.

The provider (Ollama, Anthropic, or OpenAI / any OpenAI-compatible server) comes from settings.
Re-running ingest on the same PDF with the same prompts costs nothing:
responses are keyed by (provider, model, prompt, output schema) under data/cache/llm/.
"""

import hashlib
import json
from functools import lru_cache

import httpx
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, SecretStr

from app.settings import Settings, get_settings


def chat_model(settings: Settings) -> BaseChatModel:
    """Build the configured chat model. Provider packages are imported only when selected."""
    match settings.llm_provider:
        case "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=settings.llm_temperature,
                num_predict=settings.llm_max_tokens,
            )
        case "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=settings.llm_model,
                api_key=settings.anthropic_api_key or SecretStr(""),  # presence is enforced by Settings
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
            )
        case "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=settings.llm_model,
                # Local OpenAI-compatible servers ignore the key, but the client refuses to start without one.
                api_key=settings.openai_api_key or SecretStr("not-needed"),
                base_url=settings.openai_base_url,
                temperature=settings.llm_temperature,
                max_completion_tokens=settings.llm_max_tokens,
            )


@lru_cache
def _model() -> BaseChatModel:
    return chat_model(get_settings())


def _prompt_text(name: str) -> str:
    return (get_settings().prompts_dir / f"{name}.md").read_text()


def prompt_version(name: str) -> str:
    """Short hash of the prompt file. Recorded on what the prompt produced, so output can be traced to it."""
    return hashlib.sha256(_prompt_text(name).encode()).hexdigest()[:8]


def model_label() -> str:
    settings = get_settings()
    return f"{settings.llm_provider}/{settings.llm_model}"


def load_prompt(name: str, **values: str) -> str:
    text = _prompt_text(name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def text(prompt: str) -> str:
    """Free-text completion, cached like `structured`."""
    settings = get_settings()
    key = hashlib.sha256(json.dumps([settings.llm_provider, settings.llm_model, prompt]).encode()).hexdigest()
    cached = settings.cache_dir / "llm" / f"{key}.txt"
    if cached.exists():
        return cached.read_text()
    content = _model().invoke(prompt).content
    result = (
        content
        if isinstance(content, str)
        else "".join(part if isinstance(part, str) else str(part.get("text", "")) for part in content)
    )
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(result)
    return result


def unavailable_reason(exc: BaseException) -> str | None:
    """A message for the user if `exc` means the LLM can't be used (not running, model missing, key rejected)."""
    settings = get_settings()
    provider, model = settings.llm_provider, settings.llm_model
    if isinstance(exc, httpx.TransportError | ConnectionError):
        hint = " (start it with `ollama serve` or the Ollama app)" if provider == "ollama" else ""
        return f"the language model ({provider}) isn't reachable{hint}"
    status = getattr(exc, "status_code", None)
    if status == 404 and "not found" in str(exc).lower():
        if provider == "ollama":
            return f"the model {model} isn't downloaded yet; run `ollama pull {model}`, then retry"
        return f"the model {model} doesn't exist for {provider}; check LLM_MODEL in .env"
    if status in (401, 403):
        return f"the {provider} API key was rejected; check it in .env"
    return None


def structured[T: BaseModel](prompt: str, output: type[T]) -> T:
    """Ask the model for an instance of `output` (via tool calling or JSON schema, per provider)."""
    settings = get_settings()
    schema = output.model_json_schema()
    key = hashlib.sha256(
        json.dumps([settings.llm_provider, settings.llm_model, prompt, schema], sort_keys=True).encode()
    ).hexdigest()
    cached = settings.cache_dir / "llm" / f"{key}.json"
    if cached.exists():
        return output.model_validate_json(cached.read_text())

    raw = _model().with_structured_output(output).invoke(prompt)
    result = raw if isinstance(raw, output) else output.model_validate(raw)

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(result.model_dump_json())
    return result
