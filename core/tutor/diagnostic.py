"""The diagnostic: a short adaptive quiz so the map starts coloured by what the learner already knows.

Each answer updates its topic and, through propagation, the topics around it (core.mastery.bkt.propagate).
"""

import sqlite3

from neo4j import Driver
from pydantic import BaseModel

from core.graph.space_map import SpaceMap
from core.mastery.select import pick_diagnostic_topic
from core.questions.bank import next_question
from core.questions.schema import Question, Response
from core.storage.learning import (
    Diagnostic,
    SqliteDiagnosticRepository,
    SqliteMasteryRepository,
    SqliteQuestionRepository,
)
from core.tutor.answers import AnswerResult, record_answer


class DiagnosticStep(BaseModel):
    diagnostic_id: str
    number: int  # of the question shown, from 1
    total: int
    done: bool
    question: dict[str, object] | None = None


class WrongQuestionError(ValueError):
    pass


def start(
    conn: sqlite3.Connection, driver: Driver, space: SpaceMap, user_id: str, space_id: str, total: int
) -> DiagnosticStep:
    d = SqliteDiagnosticRepository(conn).create(user_id, space_id, min(total, len(space.topics)))
    return _advance(conn, driver, space, d)


def _advance(conn: sqlite3.Connection, driver: Driver, space: SpaceMap, d: Diagnostic) -> DiagnosticStep:
    repo = SqliteDiagnosticRepository(conn)
    mastery = SqliteMasteryRepository(conn).for_space(d.user_id, d.space_id)
    question: Question | None = None
    while d.answered < d.total and question is None:
        topic_id = pick_diagnostic_topic(space, mastery, set(d.asked))
        if topic_id is None:
            break
        d.asked.append(topic_id)
        question = next_question(conn, driver, d.space_id, space.topics[topic_id], d.user_id)
    d.current_question_id = question.id if question else None
    d.status = "active" if question else "done"
    repo.save(d)
    return DiagnosticStep(
        diagnostic_id=d.id,
        number=d.answered + 1 if question else d.answered,
        total=d.total,
        done=question is None,
        question=question.public() if question else None,
    )


def answer(
    conn: sqlite3.Connection,
    driver: Driver,
    space: SpaceMap,
    d: Diagnostic,
    question_id: str,
    response: Response,
) -> tuple[AnswerResult, DiagnosticStep]:
    if d.status != "active" or d.current_question_id != question_id:
        raise WrongQuestionError("that isn't the diagnostic's current question")
    question = SqliteQuestionRepository(conn).get(question_id)
    assert question is not None
    result = record_answer(conn, space, d.user_id, d.space_id, question, response, "diagnostic")
    d.answered += 1
    return result, _advance(conn, driver, space, d)
