from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5-5"

    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5432/copilot"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "copilot-password"

    data_dir: Path = ROOT / "data"
    prompts_dir: Path = ROOT / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
