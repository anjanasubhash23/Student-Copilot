"""Mark an answer, record it, and update mastery: shared by the diagnostic and practice."""

import sqlite3
from typing import Any

from pydantic import BaseModel

from core.graph.space_map import SpaceMap
from core.marking.marking import mark
from core.mastery.bkt import LEARN, PRIOR, is_mastered, propagate, update
from core.questions.schema import Mark, Question, Response
from core.storage.learning import AttemptMode, SqliteAttemptRepository, SqliteMasteryRepository


class TopicMastery(BaseModel):
    topic_id: str
    name: str
    p_known: float
    mastered: bool


class AnswerResult(BaseModel):
    mark: Mark
    reveal: dict[str, Any]  # the answer key and explanation, now that the learner has answered
    mastery: TopicMastery  # the answered topic, after the update
    also_updated: list[TopicMastery]  # topics changed by diagnostic propagation


def reveal(q: Question) -> dict[str, Any]:
    return {
        "correct": q.correct,
        "answer": q.answer,
        "range": [q.num_low, q.num_high] if q.type == "numeric" else None,
        "explanation": q.explanation,
        "chunk_id": q.chunk_id,
    }


def _tm(space: SpaceMap, topic_id: str, p: float) -> TopicMastery:
    name = space.topics[topic_id].name if topic_id in space.topics else topic_id
    return TopicMastery(topic_id=topic_id, name=name, p_known=p, mastered=is_mastered(p))


def record_answer(
    conn: sqlite3.Connection,
    space: SpaceMap,
    user_id: str,
    space_id: str,
    question: Question,
    response: Response,
    mode: AttemptMode,
) -> AnswerResult:
    result = mark(question, response)
    SqliteAttemptRepository(conn).add(user_id, space_id, question, response, result, mode)

    repo = SqliteMasteryRepository(conn)
    mastery = repo.for_space(user_id, space_id)
    topic = question.topic_id
    p_old = mastery.get(topic, PRIOR)
    p_new = update(p_old, result.correct, question.type, learn=0.0 if mode == "diagnostic" else LEARN)
    others = propagate(space, mastery, topic, p_old, p_new) if mode == "diagnostic" else {}
    repo.set_many(user_id, space_id, {topic: p_new, **others}, cause=mode, attempted=topic)

    return AnswerResult(
        mark=result,
        reveal=reveal(question),
        mastery=_tm(space, topic, p_new),
        also_updated=[
            _tm(space, t, p) for t, p in sorted(others.items(), key=lambda kv: -abs(kv[1] - mastery.get(kv[0], PRIOR)))
        ],
    )
