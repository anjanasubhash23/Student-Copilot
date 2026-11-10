"""Flashcards are generated per topic the first time it is practised (a background job), then reused."""

import logging
import sqlite3

from neo4j import Driver

from core.graph.queries import get_space_map, topic_chunks
from core.llm import load_prompt, model_label, prompt_version, structured
from core.questions.excerpts import format_excerpts
from core.questions.schema import FlashcardsOut
from core.storage.flashcards import Flashcard, SqliteFlashcardRepository

log = logging.getLogger(__name__)

PER_TOPIC = 4


def ensure_flashcards(conn: sqlite3.Connection, driver: Driver, space_id: str, topic_id: str) -> int:
    """Generate the topic's cards unless it has some. Returns how many were added."""
    repo = SqliteFlashcardRepository(conn)
    if repo.has_topic(space_id, topic_id):
        return 0
    topic = get_space_map(space_id, driver).topics.get(topic_id)
    chunks = topic_chunks(space_id, topic_id, limit=3, driver=driver)
    if topic is None or not chunks:
        return 0
    prompt = load_prompt(
        "flashcards", topic=topic.name, summary=topic.summary, count=str(PER_TOPIC), excerpts=format_excerpts(chunks)
    )
    label = f"{model_label()} flashcards@{prompt_version('flashcards')}"
    cards = [
        Flashcard(
            space_id=space_id,
            topic_id=topic_id,
            front=c.front.strip(),
            back=c.back.strip(),
            chunk_id=chunks[c.source - 1]["id"],
            extracted_by=label,
        )
        for c in structured(prompt, FlashcardsOut).cards
        if 1 <= c.source <= len(chunks) and c.front.strip() and c.back.strip()  # must cite a real excerpt
    ]
    repo.add_many(cards)
    log.info("%s: %d flashcards", topic.name, len(cards))
    return len(cards)
