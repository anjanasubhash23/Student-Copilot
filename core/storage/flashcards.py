"""Flashcards (shared per space) and each learner's review state."""

import sqlite3
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from core.storage.clock import iso, now


class Flashcard(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    space_id: str
    topic_id: str
    front: str
    back: str
    chunk_id: str
    extracted_by: str


class DueCard(BaseModel):
    flashcard: Flashcard
    due_at: datetime | None  # None: never reviewed


class SqliteFlashcardRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add_many(self, cards: list[Flashcard]) -> None:
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO flashcards (id, space_id, topic_id, front, back, chunk_id, extracted_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (c.id, c.space_id, c.topic_id, c.front, c.back, c.chunk_id, c.extracted_by, iso(now()))
                    for c in cards
                ],
            )

    def get(self, card_id: str) -> Flashcard | None:
        row = self._conn.execute("SELECT * FROM flashcards WHERE id = ?", (card_id,)).fetchone()
        return _to_card(row) if row else None

    def has_topic(self, space_id: str, topic_id: str) -> bool:
        return (
            self._conn.execute(
                "SELECT 1 FROM flashcards WHERE space_id = ? AND topic_id = ? LIMIT 1", (space_id, topic_id)
            ).fetchone()
            is not None
        )

    def due(self, user_id: str, space_id: str, at: datetime, new_limit: int, limit: int = 50) -> list[DueCard]:
        """Reviewed cards that are due, most overdue first, then up to `new_limit` never-reviewed cards."""
        due_rows = self._conn.execute(
            """
            SELECT f.*, r.due_at FROM reviews r JOIN flashcards f ON f.id = r.flashcard_id
            WHERE r.user_id = ? AND r.space_id = ? AND r.due_at <= ?
            ORDER BY r.due_at LIMIT ?
            """,
            (user_id, space_id, iso(at), limit),
        ).fetchall()
        new_rows = self._conn.execute(
            """
            SELECT f.*, NULL AS due_at FROM flashcards f
            WHERE f.space_id = ? AND NOT EXISTS (
                SELECT 1 FROM reviews r WHERE r.user_id = ? AND r.flashcard_id = f.id)
            ORDER BY f.created_at, f.id LIMIT ?
            """,
            (space_id, user_id, new_limit),
        ).fetchall()
        return [
            DueCard(flashcard=_to_card(r), due_at=datetime.fromisoformat(r["due_at"]) if r["due_at"] else None)
            for r in [*due_rows, *new_rows]
        ]

    def reviewed_today(self, user_id: str, space_id: str, since: datetime) -> int:
        row = self._conn.execute(
            "SELECT count(*) FROM reviews WHERE user_id = ? AND space_id = ? AND last_review >= ?",
            (user_id, space_id, iso(since)),
        ).fetchone()
        return int(row[0])

    def state(self, user_id: str, card_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT card FROM reviews WHERE user_id = ? AND flashcard_id = ?", (user_id, card_id)
        ).fetchone()
        return str(row[0]) if row else None

    def save_review(self, user_id: str, card: Flashcard, state: str, due_at: datetime, at: datetime) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO reviews (user_id, flashcard_id, space_id, card, due_at, last_review)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, flashcard_id) DO UPDATE SET
                    card = excluded.card, due_at = excluded.due_at, last_review = excluded.last_review
                """,
                (user_id, card.id, card.space_id, state, iso(due_at), iso(at)),
            )

    def due_counts(self, user_id: str, space_id: str, at: datetime) -> dict[str, int]:
        """Cards due now per topic (reviewed cards only)."""
        rows = self._conn.execute(
            """
            SELECT f.topic_id, count(*) AS n FROM reviews r JOIN flashcards f ON f.id = r.flashcard_id
            WHERE r.user_id = ? AND r.space_id = ? AND r.due_at <= ? GROUP BY f.topic_id
            """,
            (user_id, space_id, iso(at)),
        ).fetchall()
        return {r["topic_id"]: r["n"] for r in rows}


def _to_card(row: sqlite3.Row) -> Flashcard:
    return Flashcard(
        id=row["id"],
        space_id=row["space_id"],
        topic_id=row["topic_id"],
        front=row["front"],
        back=row["back"],
        chunk_id=row["chunk_id"],
        extracted_by=row["extracted_by"],
    )
