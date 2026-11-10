"""A job queue in SQLite: enough for one machine, with no Redis to run.

Claiming is a single UPDATE ... RETURNING, which SQLite runs atomically, so several workers (threads or
processes) can share the queue without taking the same job twice.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from core.storage.clock import iso, now

JobKind = Literal["ingest_source", "build_graph", "flashcards"]
JobStatus = Literal["queued", "running", "done", "failed"]


class Job(BaseModel):
    id: int
    kind: JobKind
    space_id: str
    source_id: str | None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus
    stage: str | None
    progress: float
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SqliteJobQueue:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def enqueue(
        self,
        kind: JobKind,
        space_id: str,
        source_id: str | None = None,
        payload: dict[str, Any] | None = None,
        dedupe: bool = False,
    ) -> int | None:
        """Add a job. With `dedupe`, skip it (returning None) if an identical one is still queued."""
        body = json.dumps(payload or {}, sort_keys=True)
        with self._conn:
            if dedupe:
                existing = self._conn.execute(
                    """
                    SELECT id FROM jobs WHERE status = 'queued' AND kind = ? AND space_id = ?
                      AND source_id IS ? AND payload = ?
                    """,
                    (kind, space_id, source_id, body),
                ).fetchone()
                if existing:
                    return None
            cur = self._conn.execute(
                "INSERT INTO jobs (kind, space_id, source_id, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (kind, space_id, source_id, body, iso(now())),
            )
            return cur.lastrowid

    def claim(self) -> Job | None:
        with self._conn:
            row = self._conn.execute(
                """
                UPDATE jobs SET status = 'running', started_at = ?, heartbeat_at = ?
                WHERE id = (SELECT id FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1)
                RETURNING *
                """,
                (iso(now()), iso(now())),
            ).fetchone()
        return _to_job(row) if row else None

    def progress(self, job_id: int, stage: str | None = None, progress: float | None = None) -> None:
        """Record progress; also the job's heartbeat."""
        with self._conn:
            self._conn.execute(
                """
                UPDATE jobs SET stage = COALESCE(?, stage), progress = COALESCE(?, progress), heartbeat_at = ?
                WHERE id = ?
                """,
                (stage, progress, iso(now()), job_id),
            )

    def finish(self, job_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE jobs SET status = 'done', progress = 1, finished_at = ? WHERE id = ?", (iso(now()), job_id)
            )

    def fail(self, job_id: int, error: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE jobs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
                (error[:1000], iso(now()), job_id),
            )

    def requeue_stale(self, older_than: timedelta) -> int:
        """Put back jobs whose worker stopped reporting progress (it died). Returns how many.

        Jobs are idempotent, so if a slow worker was in fact still alive, running the job twice is harmless.
        """
        with self._conn:
            cur = self._conn.execute(
                """
                UPDATE jobs SET status = 'queued', started_at = NULL, heartbeat_at = NULL
                WHERE status = 'running' AND heartbeat_at < ?
                """,
                (iso(now() - older_than),),
            )
            return cur.rowcount

    def get(self, job_id: int) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _to_job(row) if row else None

    def active_for_space(self, space_id: str) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE space_id = ? AND status IN ('queued', 'running') ORDER BY id", (space_id,)
        ).fetchall()
        return [_to_job(r) for r in rows]

    def has_active(self, space_id: str, kind: JobKind, payload: dict[str, Any] | None = None) -> bool:
        query = "SELECT 1 FROM jobs WHERE space_id = ? AND kind = ? AND status IN ('queued', 'running')"
        params: tuple[Any, ...] = (space_id, kind)
        if payload is not None:
            query += " AND payload = ?"
            params += (json.dumps(payload, sort_keys=True),)
        return self._conn.execute(query, params).fetchone() is not None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        kind=row["kind"],
        space_id=row["space_id"],
        source_id=row["source_id"],
        payload=json.loads(row["payload"]),
        status=row["status"],
        stage=row["stage"],
        progress=row["progress"],
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=_dt(row["started_at"]),
        finished_at=_dt(row["finished_at"]),
    )
