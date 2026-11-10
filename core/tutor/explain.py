"""Explain mode: Graph-RAG over the space's topic graph (spec section 4).

1. Full-text search for the topic the question is about (topic names and summaries, then chunk text).
2. Walk PREREQUISITE_OF up to 2 hops back from it.
3. Keep the prerequisites the learner probably doesn't know yet (p_known < 0.95).
4. Pull chunks for the topic and those weak prerequisites.
5. Ask the LLM to cover the weak prerequisites briefly first, then answer, citing the numbered sources.
"""

from typing import Any

from neo4j import Driver
from pydantic import BaseModel

from core import llm
from core.graph.queries import search_chunks, search_topics, topic_chunks
from core.graph.space_map import SpaceMap
from core.mastery.bkt import MASTERED, PRIOR
from core.questions.excerpts import location, neutralize

PREREQ_HOPS = 2
MAX_WEAK_PREREQS = 3
TOPIC_CHUNKS = 3

NO_MATCH = "I couldn't find anything about that in this space's sources. Try asking with the terms your notes use."


class Citation(BaseModel):
    n: int
    chunk_id: str
    source: str
    location: str
    topic: str | None


class Explanation(BaseModel):
    answer: str
    topic: str | None
    covered_prerequisites: list[str]
    citations: list[Citation]


def find_topic(space_id: str, question: str, space: SpaceMap, driver: Driver) -> str | None:
    for hit in search_topics(space_id, question, limit=3, driver=driver):
        if hit["id"] in space.topics:
            return str(hit["id"])
    for chunk in search_chunks(space_id, question, limit=1, driver=driver):
        for tid in chunk["topics"]:
            if tid in space.topics:
                return str(tid)
    return None


def weak_prerequisites(space: SpaceMap, topic_id: str, mastery: dict[str, float]) -> list[str]:
    """Prerequisites within PREREQ_HOPS the learner hasn't mastered, nearest and weakest first."""
    nearby = space.ancestors(topic_id, PREREQ_HOPS)
    weak = [t for t in nearby if mastery.get(t, PRIOR) < MASTERED]
    weak.sort(key=lambda t: (nearby[t], mastery.get(t, PRIOR), space.topics[t].first_seen))
    # deepest first in the prompt, so the explanation builds up to the topic
    return list(reversed(weak[:MAX_WEAK_PREREQS]))


def format_sources(chunks: list[tuple[dict[str, Any], str]]) -> str:
    return "\n\n".join(
        f'<source n="{i}" from="{neutralize(c["source"] or "", "source")} {location(c)}" topic="{topic}">\n'
        f"{neutralize(c['text'], 'source')}\n</source>"
        for i, (c, topic) in enumerate(chunks, start=1)
    )


def explain(space_id: str, question: str, space: SpaceMap, mastery: dict[str, float], driver: Driver) -> Explanation:
    topic_id = find_topic(space_id, question, space, driver)
    if topic_id is None:
        return Explanation(answer=NO_MATCH, topic=None, covered_prerequisites=[], citations=[])
    topic = space.topics[topic_id]
    weak = weak_prerequisites(space, topic_id, mastery)

    picked: list[tuple[dict[str, Any], str]] = []
    seen: set[str] = set()

    def add(chunks: list[dict[str, Any]], topic_name: str) -> None:
        for c in chunks:
            if c["id"] not in seen:
                seen.add(c["id"])
                picked.append((c, topic_name))

    for pre in weak:
        add(topic_chunks(space_id, pre, limit=1, driver=driver), space.topics[pre].name)
    add(search_chunks(space_id, question, topic_ids=[topic_id], limit=TOPIC_CHUNKS, driver=driver), topic.name)
    if len(picked) - len(weak) < TOPIC_CHUNKS:
        add(topic_chunks(space_id, topic_id, limit=TOPIC_CHUNKS, driver=driver), topic.name)

    names = [space.topics[t].name for t in weak]
    note = (
        f"The question is about {topic.name}. The student hasn't mastered these prerequisites yet: "
        f"{', '.join(names)}. Start with a brief explanation of each (a few sentences), then answer the question."
        if names
        else f"The question is about {topic.name}. The student knows its prerequisites; answer directly."
    )
    prompt = llm.load_prompt(
        "explain", prerequisite_note=note, sources=format_sources(picked), question=neutralize(question, "question")
    )
    answer = llm.text(prompt).strip()
    citations = [
        Citation(n=i, chunk_id=c["id"], source=c["source"] or "", location=location(c), topic=topic_name)
        for i, (c, topic_name) in enumerate(picked, start=1)
    ]
    return Explanation(answer=answer, topic=topic.name, covered_prerequisites=names, citations=citations)
