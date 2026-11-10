"""Practice: questions on the weakest topics whose prerequisites are ready."""

import sqlite3

from neo4j import Driver

from core.graph.space_map import SpaceMap
from core.mastery.select import pick_practice_topic
from core.questions.bank import next_question
from core.questions.schema import Question
from core.storage.learning import SqliteAttemptRepository, SqliteMasteryRepository

MAX_TOPICS_TRIED = 5  # topics without usable material are skipped; give up after this many


def next_practice_question(
    conn: sqlite3.Connection,
    driver: Driver,
    space: SpaceMap,
    user_id: str,
    space_id: str,
    topic_id: str | None = None,
) -> Question | None:
    """A question on `topic_id` if given (the learner picked it on the map), else on the topic most worth practising."""
    if topic_id is not None:
        return (
            next_question(conn, driver, space_id, space.topics[topic_id], user_id) if topic_id in space.topics else None
        )
    mastery = SqliteMasteryRepository(conn).for_space(user_id, space_id)
    recent = SqliteAttemptRepository(conn).recent(user_id, space_id, limit=1)
    avoid = {recent[0].topic_id} if recent else set()
    for _ in range(MAX_TOPICS_TRIED):
        chosen = pick_practice_topic(space, mastery, avoid)
        if chosen is None:
            return None
        question = next_question(conn, driver, space_id, space.topics[chosen], user_id)
        if question is not None:
            return question
        # no usable material for this topic: treat it as done for this pick, so the next-best is chosen
        mastery = {**mastery, chosen: 1.0}
    return None
