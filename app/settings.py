"""Typed configuration, loaded from environment variables and `.env`.

Secrets are `SecretStr` so they never appear in reprs, logs or tracebacks;
call `.get_secret_value()` only at the point where the secret is handed to a client.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

NEO4J_SCHEMES = ("bolt", "bolt+s", "bolt+ssc", "neo4j", "neo4j+s", "neo4j+ssc")


class Settings(BaseSettings):
    # hide_input_in_errors: a ValidationError would otherwise echo the raw value of a bad secret.
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-5-5"
    llm_concurrency: int = Field(default=4, ge=1, le=32)

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr

    prompts_dir: Path = ROOT / "prompts"
    cache_dir: Path = ROOT / "data" / "cache"

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
