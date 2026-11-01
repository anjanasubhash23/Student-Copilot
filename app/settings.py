"""Typed configuration, loaded from environment variables and `.env`.

Secrets are `SecretStr` so they never appear in reprs, logs or tracebacks;
call `.get_secret_value()` only at the point where the secret is handed to a client.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

NEO4J_SCHEMES = ("bolt", "bolt+s", "bolt+ssc", "neo4j", "neo4j+s", "neo4j+ssc")

LLMProvider = Literal["ollama", "anthropic", "openai"]

# Used when LLM_MODEL is unset. "openai" has none: it also covers OpenAI-compatible
# servers (via OPENAI_BASE_URL), so the model name must be given explicitly.
DEFAULT_MODELS: dict[LLMProvider, str] = {
    "ollama": "llama3.1:8b",
    "anthropic": "claude-sonnet-5-5",
}


class Settings(BaseSettings):
    # hide_input_in_errors: a ValidationError would otherwise echo the raw value of a bad secret.
    # env_ignore_empty: `OPENAI_BASE_URL=` in .env means "unset", not "the empty string".
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True, env_ignore_empty=True
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    llm_provider: LLMProvider = "ollama"
    llm_model: str = ""
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=8192, ge=1)
    llm_concurrency: int = Field(default=4, ge=1, le=32)
    ollama_base_url: str = "http://localhost:11434"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr

    sqlite_path: Path = ROOT / "data" / "app.db"

    prompts_dir: Path = ROOT / "prompts"
    cache_dir: Path = ROOT / "data" / "cache"

    @field_validator("sqlite_path")
    @classmethod
    def _resolve_sqlite_path(cls, path: Path) -> Path:
        # Relative paths are relative to the project root, not to wherever the process was started.
        return path if path.is_absolute() else ROOT / path

    @model_validator(mode="after")
    def _check_llm(self) -> "Settings":
        if not self.llm_model:
            if self.llm_provider not in DEFAULT_MODELS:
                raise ValueError(f"LLM_MODEL is required when LLM_PROVIDER={self.llm_provider}")
            self.llm_model = DEFAULT_MODELS[self.llm_provider]
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        # A custom base URL may point at a local server that needs no key.
        if self.llm_provider == "openai" and not self.openai_api_key and not self.openai_base_url:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai (unless OPENAI_BASE_URL is set)")
        return self

    @field_validator("neo4j_uri")
    @classmethod
    def _check_neo4j_scheme(cls, uri: str) -> str:
        scheme = uri.partition("://")[0]
        if scheme not in NEO4J_SCHEMES:
            raise ValueError(f"scheme must be one of {', '.join(NEO4J_SCHEMES)}; got {scheme!r}")
        return uri

    @field_validator("neo4j_password")
    @classmethod
    def _check_neo4j_password(cls, password: SecretStr) -> SecretStr:
        # Neo4j 5 refuses to start with a password shorter than 8 characters.
        if len(password.get_secret_value()) < 8:
            raise ValueError("must be at least 8 characters")
        return password


@lru_cache
def get_settings() -> Settings:
    return Settings()
