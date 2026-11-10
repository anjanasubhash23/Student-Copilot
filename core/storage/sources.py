"""Sources added to a study space, and how far each has got through ingestion."""

import sqlite3
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from core.ingest.schema import SourceKind, SourceRef
from core.storage.clock import iso, now

SourceStatus = Literal["queued", "processing", "ready", "failed"]


class Source(BaseModel):
    id: str
    space_id: str
    kind: SourceKind
    name: str
    uri: str | None = None  # the link, for web and YouTube sources
    storage_path: str | None = None  # the stored upload, for file sources
    content_hash: str | None = None
    pages: int | None = None
    status: SourceStatus = "queued"
    stage: str | None = None
    progress: float = 0.0
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def new(cls, space_id: str, kind: SourceKind, name: str, **fields: str | None) -> "Source":
        at = now()
        return cls(id=uuid4().hex[:16], space_id=space_id, kind=kind, name=name, created_at=at, updated_at=at, **fields)

    @property
    def ref(self) -> SourceRef:
        return SourceRef(id=self.id, name=self.name, kind=self.kind)


COLUMNS = (
    "id, space_id, kind, name, uri, storage_path, content_hash, pages, status, stage, progress, error, "
    "created_at, updated_at"
)


class SqliteSourceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, s: Source) -> None:
        with self._conn:
            self._conn.execute(
                f"INSERT INTO sources ({COLUMNS}) VALUES ({', '.join('?' * 14)})",
                (
                    s.id,
                    s.space_id,
                    s.kind,
                    s.name,
                    s.uri,
                    s.storage_path,
                    s.content_hash,
                    s.pages,
                    s.status,
                    s.stage,
                    s.progress,
                    s.error,
                    iso(s.created_at),
                    iso(s.updated_at),
                ),
            )

    def get(self, source_id: str) -> Source | None:
        row = self._conn.execute(f"SELECT {COLUMNS} FROM sources WHERE id = ?", (source_id,)).fetchone()
        return _to_source(row) if row else None

    def list_for_space(self, space_id: str) -> list[Source]:
        rows = self._conn.execute(
            f"SELECT {COLUMNS} FROM sources WHERE space_id = ? ORDER BY created_at, id", (space_id,)
        ).fetchall()
        return [_to_source(r) for r in rows]

    def find_by_hash(self, space_id: str, content_hash: str) -> Source | None:
        row = self._conn.execute(
            f"SELECT {COLUMNS} FROM sources WHERE space_id = ? AND content_hash = ? AND status != 'failed'",
            (space_id, content_hash),
        ).fetchone()
        return _to_source(row) if row else None

    def update(self, source_id: str, **fields: object) -> None:
        allowed = {"name", "status", "stage", "progress", "error", "pages", "content_hash"}
        if not fields or not set(fields) <= allowed:
            raise ValueError(f"can only update {sorted(allowed)}")
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._conn:
            self._conn.execute(
                f"UPDATE sources SET {assignments}, updated_at = ? WHERE id = ?",
                (*fields.values(), iso(now()), source_id),
            )

    def delete(self, source_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


def _to_source(row: sqlite3.Row) -> Source:
    return Source(
        **{k: row[k] for k in row.keys() if k not in ("created_at", "updated_at")},  # noqa: SIM118 (iterating a Row gives values)
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
