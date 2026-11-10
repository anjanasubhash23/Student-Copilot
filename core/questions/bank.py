"""Questions are generated lazily, the first time a topic is practised, then reused."""

import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from neo4j import Driver

from app.settings import get_settings
from core.graph.queries import topic_chunks
from core.graph.space_map import TopicInfo
from core.llm import load_prompt, model_label, prompt_version, structured
from core.questions.excerpts import format_excerpts
from core.questions.schema import Question, QuestionsOut
from core.questions.validate import to_question
from core.storage.learning import SqliteAttemptRepository, SqliteQuestionRepository

log = logging.getLogger(__name__)

PER_ROUND = 4
MAX_ROUNDS = 3  # rounds of generation per topic; after that, questions are repeated


def generate(space_id: str, topic: TopicInfo, chunks: list[dict[str, Any]], avoid: list[str]) -> list[Question]:
    settings = get_settings()
    avoid_note = (
        "\nDon't repeat these questions, which the student has already seen:\n" + "\n".join(f"- {s}" for s in avoid)
        if avoid
        else ""
    )
    prompt = load_prompt(
        "questions",
        topic=topic.name,
        summary=topic.summary,
        count=str(PER_ROUND),
        avoid=avoid_note,
        excerpts=format_excerpts(chunks),
    )
    drafts = structured(prompt, QuestionsOut).questions
    label = f"{model_label()} questions@{prompt_version('questions')}"

    def check(d: Any) -> Question:
        return to_question(
            d,
            space_id=space_id,
            topic_id=topic.id,
            topic_name=topic.name,
            chunks=chunks,
            extracted_by=label,
            timeout=settings.numeric_timeout_seconds,
        )

    with ThreadPoolExecutor(settings.llm_concurrency) as pool:
        questions = list(pool.map(check, drafts))
    log.info("%s: %d/%d questions valid", topic.name, sum(q.status == "valid" for q in questions), len(questions))
    return questions


def next_question(
    conn: sqlite3.Connection, driver: Driver, space_id: str, topic: TopicInfo, user_id: str
) -> Question | None:
    """An unanswered valid question on the topic, generating more if needed; else the least recently seen one."""
    repo, attempts = SqliteQuestionRepository(conn), SqliteAttemptRepository(conn)
    answered = attempts.answered_question_ids(user_id, space_id, topic.id)
    for _ in range(MAX_ROUNDS + 1):
        valid = repo.valid_for_topic(space_id, topic.id)
        fresh = [q for q in valid if q.id not in answered]
        if fresh:
            return fresh[0]
        if repo.count_for_topic(space_id, topic.id) >= PER_ROUND * MAX_ROUNDS:
            break
        chunks = topic_chunks(space_id, topic.id, limit=3, driver=driver)
        if not chunks:
            return None
        made = generate(space_id, topic, chunks, avoid=[q.stem for q in valid])
        if not made:
            break
        repo.add_many(made)
    valid = repo.valid_for_topic(space_id, topic.id)
    if not valid:
        return None
    # attempts come newest first; the first sighting of a question is its most recent one
    last_seen: dict[str, int] = {}
    for age, attempt in enumerate(attempts.recent(user_id, space_id, limit=200)):
        last_seen.setdefault(attempt.question_id, age)
    return max(valid, key=lambda q: last_seen.get(q.id, 10**6))
