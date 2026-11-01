import sqlite3
from datetime import datetime

from core.spaces.models import StudySpace
from core.spaces.repository import AlreadyExistsError


class SqliteStudySpaceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, space: StudySpace) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO study_spaces (id, name, created_at) VALUES (?, ?, ?)",
                    (space.id, space.name, space.created_at.isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise AlreadyExistsError(f"study space {space.id} already exists") from exc

    def get(self, space_id: str) -> StudySpace | None:
        row = self._conn.execute("SELECT * FROM study_spaces WHERE id = ?", (space_id,)).fetchone()
        return _to_space(row) if row else None

    def list_all(self) -> list[StudySpace]:
        rows = self._conn.execute("SELECT * FROM study_spaces ORDER BY created_at, id").fetchall()
        return [_to_space(row) for row in rows]


def _to_space(row: sqlite3.Row) -> StudySpace:
    return StudySpace(id=row["id"], name=row["name"], created_at=datetime.fromisoformat(row["created_at"]))
