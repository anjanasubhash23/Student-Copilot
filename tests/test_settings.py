import pytest
from pydantic import ValidationError

from app.settings import ROOT, Settings


def _load(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_reads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEO4J_PASSWORD", "from-the-env")
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://graph.example.com")
    monkeypatch.setenv("LLM_CONCURRENCY", "8")
    s = _load()
    assert s.neo4j_password.get_secret_value() == "from-the-env"
    assert s.neo4j_uri == "neo4j+s://graph.example.com"
    assert s.llm_concurrency == 8
    assert s.anthropic_api_key is None


def test_env_example_is_valid() -> None:
    s = Settings(_env_file=ROOT / ".env.example")
    assert s.app_env == "development"
    assert s.neo4j_uri == "bolt://localhost:7687"
    assert s.neo4j_password.get_secret_value() == "change-me-local-dev"
    assert not s.anthropic_api_key


def test_neo4j_password_is_required() -> None:
    with pytest.raises(ValidationError, match="neo4j_password"):
        _load()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("neo4j_uri", "http://localhost:7474"),
        ("neo4j_uri", "localhost:7687"),
        ("llm_concurrency", 0),
        ("app_env", "staging"),
        ("log_level", "verbose"),
    ],
)
def test_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        _load(neo4j_password="test-password", **{field: value})


def test_rejects_short_password_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _load(neo4j_password="hunter2")
    assert "at least 8 characters" in str(exc_info.value)
    assert "hunter2" not in str(exc_info.value)


def test_secrets_are_masked_in_repr() -> None:
    s = _load(neo4j_password="super-secret-pw", anthropic_api_key="sk-ant-secret")
    assert "super-secret-pw" not in repr(s)
    assert "sk-ant-secret" not in repr(s)
