"""The learning loop: diagnostic, practice, explain, progress."""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import CurrentUser, Db, LlmBudget, Map, Neo4j, SettingsDep, Space
from core.graph.queries import get_chunks
from core.marking.marking import InvalidResponseError
from core.mastery.bkt import MASTERED, PRIOR
from core.mastery.progress import mastered_by_day
from core.questions.excerpts import location
from core.questions.schema import Question, Response
from core.storage.clock import now
from core.storage.flashcards import SqliteFlashcardRepository
from core.storage.jobs import SqliteJobQueue
from core.storage.learning import (
    SqliteAttemptRepository,
    SqliteDiagnosticRepository,
    SqliteMasteryRepository,
    SqliteQuestionRepository,
)
from core.tutor import diagnostic
from core.tutor.answers import AnswerResult, record_answer
from core.tutor.explain import Explanation, explain
from core.tutor.practice import next_practice_question

router = APIRouter(prefix="/spaces/{space_id}", tags=["learning"])


class AnswerIn(BaseModel):
    question_id: str
    response: Response


class AnswerOut(AnswerResult):
    source: dict[str, Any] | None = None  # where the question came from, for "see in your notes"


def _with_source(result: AnswerResult, space_id: str, driver: Neo4j) -> AnswerOut:
    chunks = get_chunks(space_id, [result.reveal["chunk_id"]], driver)
    source = {"name": chunks[0]["source"], "location": location(chunks[0])} if chunks else None
    return AnswerOut(**result.model_dump(), source=source)


def _question(conn: Db, space_id: str, question_id: str) -> Question:
    q = SqliteQuestionRepository(conn).get(question_id)
    if q is None or q.space_id != space_id or q.status != "valid":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    return q


# Diagnostic


@router.post("/diagnostic", dependencies=[LlmBudget])
def start_diagnostic(
    space: Space, space_map: Map, user: CurrentUser, conn: Db, driver: Neo4j, settings: SettingsDep
) -> diagnostic.DiagnosticStep:
    """Start the adaptive diagnostic; returns the first question."""
    step = diagnostic.start(conn, driver, space_map, user.id, space.id, settings.diagnostic_questions)
    if step.done and step.number == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "couldn't make diagnostic questions from these sources")
    return step


class DiagnosticAnswerOut(BaseModel):
    result: AnswerOut
    next: diagnostic.DiagnosticStep


@router.post("/diagnostic/{diagnostic_id}/answer", dependencies=[LlmBudget])
def answer_diagnostic(
    diagnostic_id: str, body: AnswerIn, space: Space, space_map: Map, user: CurrentUser, conn: Db, driver: Neo4j
) -> DiagnosticAnswerOut:
    d = SqliteDiagnosticRepository(conn).get(diagnostic_id)
    if d is None or d.user_id != user.id or d.space_id != space.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "diagnostic not found")
    _question(conn, space.id, body.question_id)
    try:
        result, step = diagnostic.answer(conn, driver, space_map, d, body.question_id, body.response)
    except diagnostic.WrongQuestionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidResponseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return DiagnosticAnswerOut(result=_with_source(result, space.id, driver), next=step)


# Practice


class PracticeNextIn(BaseModel):
    topic_id: str | None = Field(default=None, description="Practise this topic instead of the one picked for you.")


class PracticeNextOut(BaseModel):
    question: dict[str, Any] | None
    topic: str | None
    message: str | None = None


@router.post("/practice/next", dependencies=[LlmBudget])
def practice_next(
    body: PracticeNextIn, space: Space, space_map: Map, user: CurrentUser, conn: Db, driver: Neo4j
) -> PracticeNextOut:
    q = next_practice_question(conn, driver, space_map, user.id, space.id, body.topic_id)
    if q is None:
        message = (
            "couldn't make questions for that topic"
            if body.topic_id
            else "every topic is mastered, or none had material to make questions from"
        )
        return PracticeNextOut(question=None, topic=None, message=message)
    return PracticeNextOut(question=q.public(), topic=space_map.topics[q.topic_id].name)


@router.post("/practice/answer", dependencies=[LlmBudget])
def practice_answer(
    body: AnswerIn, space: Space, space_map: Map, user: CurrentUser, conn: Db, driver: Neo4j
) -> AnswerOut:
    q = _question(conn, space.id, body.question_id)
    try:
        result = record_answer(conn, space_map, user.id, space.id, q, body.response, "practice")
    except InvalidResponseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    # Flashcards are made the first time a topic is practised, in the background.
    if not SqliteFlashcardRepository(conn).has_topic(space.id, q.topic_id):
        SqliteJobQueue(conn).enqueue("flashcards", space.id, payload={"topic_id": q.topic_id}, dedupe=True)
    return _with_source(result, space.id, driver)


# Explain


class ExplainIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


@router.post("/explain", dependencies=[LlmBudget])
def explain_question(
    body: ExplainIn, space: Space, space_map: Map, user: CurrentUser, conn: Db, driver: Neo4j
) -> Explanation:
    """Answer from the space's sources with citations, covering weak prerequisites first."""
    mastery = SqliteMasteryRepository(conn).for_space(user.id, space.id)
    return explain(space.id, body.question, space_map, mastery, driver)


# Progress


@router.get("/progress")
def progress(space: Space, space_map: Map, user: CurrentUser, conn: Db) -> dict[str, Any]:
    mastery = SqliteMasteryRepository(conn).for_space(user.id, space.id)
    history = SqliteMasteryRepository(conn).history(user.id, space.id)
    recent = SqliteAttemptRepository(conn).recent(user.id, space.id, limit=50)
    cards = SqliteFlashcardRepository(conn)
    at = now()
    due = cards.due_counts(user.id, space.id, at)
    weakest = sorted(
        (t for t in space_map.topics.values() if mastery.get(t.id, PRIOR) < MASTERED),
        key=lambda t: mastery.get(t.id, PRIOR),
    )[:5]
    return {
        "topics": len(space_map.topics),
        "mastered": sum(mastery.get(t, PRIOR) >= MASTERED for t in space_map.topics),
        "assessed": sum(t in mastery for t in space_map.topics),
        "mastered_over_time": [d for d in mastered_by_day(history)],
        "recent_accuracy": round(sum(a.correct for a in recent) / len(recent), 3) if recent else None,
        "attempts": len(recent),
        "weakest": [{"id": t.id, "name": t.name, "p_known": round(mastery.get(t.id, PRIOR), 4)} for t in weakest],
        "due_for_review": [
            {"id": tid, "name": space_map.topics[tid].name, "cards": n}
            for tid, n in due.items()
            if tid in space_map.topics
        ],
        "reviewed_today": cards.reviewed_today(user.id, space.id, at - timedelta(days=1)),
    }
