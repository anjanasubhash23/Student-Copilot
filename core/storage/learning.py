"""Questions, attempts, mastery and diagnostic sessions."""

import json
import sqlite3
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel

from core.questions.schema import Mark, Question, Response
from core.storage.clock import iso, now

AttemptMode = Literal["diagnostic", "practice"]

Q_JSON = ("options", "correct", "validation")
Q_COLUMNS = (
    "id",
    "space_id",
    "topic_id",
    "type",
    "stem",
    "options",
    "correct",
    "answer",
    "num_low",
    "num_high",
    "rubric",
    "explanation",
    "solution_code",
    "chunk_id",
    "validation",
    "status",
    "extracted_by",
    "created_at",
)


class SqliteQuestionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add_many(self, questions: list[Question]) -> None:
        with self._conn:
            self._conn.executemany(
                f"INSERT INTO questions ({', '.join(Q_COLUMNS)}) VALUES ({', '.join('?' * len(Q_COLUMNS))})",
                [_question_row(q) for q in questions],
            )

    def get(self, question_id: str) -> Question | None:
        row = self._conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return _to_question(row) if row else None

    def valid_for_topic(self, space_id: str, topic_id: str) -> list[Question]:
        rows = self._conn.execute(
            "SELECT * FROM questions WHERE space_id = ? AND topic_id = ? AND status = 'valid' ORDER BY created_at",
            (space_id, topic_id),
        ).fetchall()
        return [_to_question(r) for r in rows]

    def count_for_topic(self, space_id: str, topic_id: str) -> int:
        """All generated questions, rejected included: tells whether generation already ran."""
        row = self._conn.execute(
            "SELECT count(*) FROM questions WHERE space_id = ? AND topic_id = ?", (space_id, topic_id)
        ).fetchone()
        return int(row[0])


def _question_row(q: Question) -> tuple[Any, ...]:
    data = q.model_dump()
    return tuple(
        json.dumps(data[c]) if c in Q_JSON else iso(data[c]) if c == "created_at" else data[c] for c in Q_COLUMNS
    )


def _to_question(row: sqlite3.Row) -> Question:
    data = {c: row[c] for c in Q_COLUMNS}
    for c in Q_JSON:
        data[c] = json.loads(data[c])
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return Question(**data)


class Attempt(BaseModel):
    question_id: str
    topic_id: str
    correct: bool
    score: float
    mode: AttemptMode
    ts: datetime


class SqliteAttemptRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self, user_id: str, space_id: str, question: Question, response: Response, mark: Mark, mode: AttemptMode
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO attempts (user_id, space_id, question_id, topic_id, response, correct, score, mode, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    space_id,
                    question.id,
                    question.topic_id,
                    response.model_dump_json(exclude_none=True),
                    int(mark.correct),
                    mark.score,
                    mode,
                    iso(now()),
                ),
            )

    def recent(self, user_id: str, space_id: str, limit: int = 20) -> list[Attempt]:
        rows = self._conn.execute(
            """
            SELECT question_id, topic_id, correct, score, mode, ts FROM attempts
            WHERE user_id = ? AND space_id = ? ORDER BY id DESC LIMIT ?
            """,
            (user_id, space_id, limit),
        ).fetchall()
        return [
            Attempt(
                question_id=r["question_id"],
                topic_id=r["topic_id"],
                correct=bool(r["correct"]),
                score=r["score"],
                mode=r["mode"],
                ts=datetime.fromisoformat(r["ts"]),
            )
            for r in rows
        ]

    def answered_question_ids(self, user_id: str, space_id: str, topic_id: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT question_id FROM attempts WHERE user_id = ? AND space_id = ? AND topic_id = ?",
            (user_id, space_id, topic_id),
        ).fetchall()
        return {r[0] for r in rows}


class MasteryEvent(BaseModel):
    topic_id: str
    p_known: float
    cause: str
    ts: datetime


class SqliteMasteryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def for_space(self, user_id: str, space_id: str) -> dict[str, float]:
        rows = self._conn.execute(
            "SELECT topic_id, p_known FROM mastery WHERE user_id = ? AND space_id = ?", (user_id, space_id)
        ).fetchall()
        return {r["topic_id"]: r["p_known"] for r in rows}

    def attempts_per_topic(self, user_id: str, space_id: str) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT topic_id, n_attempts FROM mastery WHERE user_id = ? AND space_id = ?", (user_id, space_id)
        ).fetchall()
        return {r["topic_id"]: r["n_attempts"] for r in rows}

    def set_many(
        self, user_id: str, space_id: str, values: dict[str, float], cause: str, attempted: str | None = None
    ) -> None:
        """Write new p_known values and log each change. `attempted`: the topic that was answered, if any."""
        at = iso(now())
        with self._conn:
            for topic_id, p in values.items():
                self._conn.execute(
                    """
                    INSERT INTO mastery (user_id, space_id, topic_id, p_known, n_attempts, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, topic_id) DO UPDATE SET
                        p_known = excluded.p_known,
                        n_attempts = n_attempts + excluded.n_attempts,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, space_id, topic_id, p, int(topic_id == attempted), at),
                )
                self._conn.execute(
                    """
                    INSERT INTO mastery_events (user_id, space_id, topic_id, p_known, cause, ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, space_id, topic_id, p, cause, at),
                )

    def history(self, user_id: str, space_id: str) -> list[MasteryEvent]:
        rows = self._conn.execute(
            """
            SELECT topic_id, p_known, cause, ts FROM mastery_events
            WHERE user_id = ? AND space_id = ? ORDER BY id
            """,
            (user_id, space_id),
        ).fetchall()
        return [
            MasteryEvent(
                topic_id=r["topic_id"], p_known=r["p_known"], cause=r["cause"], ts=datetime.fromisoformat(r["ts"])
            )
            for r in rows
        ]


class Diagnostic(BaseModel):
    id: str
    user_id: str
    space_id: str
    asked: list[str]  # topic ids tried, in order (including any skipped for lack of a question)
    current_question_id: str | None
    answered: int = 0
    total: int
    status: Literal["active", "done"]


class SqliteDiagnosticRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, user_id: str, space_id: str, total: int) -> Diagnostic:
        d = Diagnostic(
            id=uuid4().hex,
            user_id=user_id,
            space_id=space_id,
            asked=[],
            current_question_id=None,
            total=total,
            status="active",
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO diagnostics (id, user_id, space_id, asked, current_question_id, total, status, created_at)
                VALUES (?, ?, ?, '[]', NULL, ?, 'active', ?)
                """,
                (d.id, user_id, space_id, total, iso(now())),
            )
        return d

    def get(self, diagnostic_id: str) -> Diagnostic | None:
        row = self._conn.execute("SELECT * FROM diagnostics WHERE id = ?", (diagnostic_id,)).fetchone()
        if row is None:
            return None
        return Diagnostic(
            id=row["id"],
            user_id=row["user_id"],
            space_id=row["space_id"],
            asked=json.loads(row["asked"]),
            current_question_id=row["current_question_id"],
            answered=row["answered"],
            total=row["total"],
            status=row["status"],
        )

    def save(self, d: Diagnostic) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE diagnostics SET asked = ?, current_question_id = ?, answered = ?, status = ? WHERE id = ?",
                (json.dumps(d.asked), d.current_question_id, d.answered, d.status, d.id),
            )
