"""Claude calls that return validated pydantic objects, cached on disk.

Re-running ingest on the same PDF with the same prompts costs nothing:
responses are keyed by (model, prompt, output schema) under data/cache/llm/.
"""

import hashlib
import json
from functools import lru_cache
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from app.settings import get_settings

T = TypeVar("T", bound=BaseModel)


@lru_cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key or None)


def load_prompt(name: str, **values: str) -> str:
    text = (get_settings().prompts_dir / f"{name}.md").read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def structured(prompt: str, output: type[T], *, max_tokens: int = 8192) -> T:
    """Force a single tool call whose input schema is `output`, and parse it."""
    settings = get_settings()
    schema = output.model_json_schema()
    key = hashlib.sha256(json.dumps([settings.llm_model, prompt, schema], sort_keys=True).encode()).hexdigest()
    cached = settings.cache_dir / "llm" / f"{key}.json"
    if cached.exists():
        return output.model_validate_json(cached.read_text())

    msg = _client().messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        tools=[{"name": "submit", "description": "Submit the result.", "input_schema": schema}],
        tool_choice={"type": "tool", "name": "submit"},
        messages=[{"role": "user", "content": prompt}],
    )
    block = next(b for b in msg.content if b.type == "tool_use")
    result = output.model_validate(block.input)

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(result.model_dump_json())
    return result
