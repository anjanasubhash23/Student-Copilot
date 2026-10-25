"""LLM extraction: chunks → topics, topics → prerequisite edges."""

import json
from dataclasses import dataclass

import anthropic

from core.config import get_settings
from core.ingest.pdf import Chunk
from core.prompts import load_prompt


@dataclass
class Topic:
    name: str
    summary: str
    pages: list[int]


@dataclass
class Prereq:
    topic: str
    requires: str


def _ask_json(prompt: str) -> dict:
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.llm_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return json.loads(text[text.find("{") : text.rfind("}") + 1])


def extract_topics(chunks: list[Chunk]) -> list[Topic]:
    template = load_prompt("extract_topics")
    topics: dict[str, Topic] = {}
    for chunk in chunks:
        out = _ask_json(template.replace("{{chunk}}", chunk.text))
        for t in out.get("topics", []):
            key = t["name"].strip().lower()
            if key in topics:
                topics[key].pages.append(chunk.page)
            else:
                topics[key] = Topic(t["name"].strip(), t.get("summary", ""), [chunk.page])
    return list(topics.values())


def extract_prereqs(topics: list[Topic]) -> list[Prereq]:
    names = {t.name for t in topics}
    listing = "\n".join(f"- {t.name}: {t.summary}" for t in topics)
    out = _ask_json(load_prompt("extract_prereqs").replace("{{topics}}", listing))
    return [
        Prereq(e["topic"], e["requires"])
        for e in out.get("edges", [])
        if e["topic"] in names and e["requires"] in names and e["topic"] != e["requires"]
    ]
