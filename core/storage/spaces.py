import sqlite3
from datetime import datetime

from core.spaces.models import GraphStatus, StudySpace
from core.spaces.repository import AlreadyExistsError


class SqliteStudySpaceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, space: StudySpace) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO study_spaces (id, name, created_at, owner_id, exam_style, graph_status, graph_error)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        space.id,
                        space.name,
                        space.created_at.isoformat(),
                        space.owner_id,
                        space.exam_style,
                        space.graph_status,
                        space.graph_error,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AlreadyExistsError(f"study space {space.id} already exists") from exc

    def get(self, space_id: str) -> StudySpace | None:
        row = self._conn.execute("SELECT * FROM study_spaces WHERE id = ?", (space_id,)).fetchone()
        return _to_space(row) if row else None

    def list_all(self) -> list[StudySpace]:
        rows = self._conn.execute("SELECT * FROM study_spaces ORDER BY created_at, id").fetchall()
        return [_to_space(row) for row in rows]

    def list_for_owner(self, owner_id: str) -> list[StudySpace]:
        rows = self._conn.execute(
            "SELECT * FROM study_spaces WHERE owner_id = ? ORDER BY created_at, id", (owner_id,)
        ).fetchall()
        return [_to_space(row) for row in rows]

    def set_graph_status(self, space_id: str, status: GraphStatus, error: str | None = None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE study_spaces SET graph_status = ?, graph_error = ? WHERE id = ?", (status, error, space_id)
            )

    def delete(self, space_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM study_spaces WHERE id = ?", (space_id,))


def _to_space(row: sqlite3.Row) -> StudySpace:
    return StudySpace(
        id=row["id"],
        name=row["name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        owner_id=row["owner_id"],
        exam_style=row["exam_style"],
        graph_status=row["graph_status"],
        graph_error=row["graph_error"],
    )
