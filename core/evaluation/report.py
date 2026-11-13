"""Ingestion time and LLM usage per source, from the job table (spec target: 100 pages in < 5 min, < $0.20)."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass
class IngestRow:
    space: str
    source: str
    kind: str
    pages: int
    seconds: float  # reading + topic extraction, plus this space's latest graph build
    llm_calls: int
    llm_cached: int
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def seconds_per_100_pages(self) -> float | None:
        return self.seconds / self.pages * 100 if self.pages else None


def _seconds(start: str | None, end: str | None) -> float:
    if not start or not end:
        return 0.0
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def ingest_report(conn: sqlite3.Connection, space_id: str | None = None) -> list[IngestRow]:
    """One row per ready source. The space's latest successful graph build is added to each of its sources:
    it is shared work, so for a one-source space the row is the full time to "ready"."""
    where, params = ("AND s.space_id = ?", (space_id,)) if space_id else ("", ())
    sources = conn.execute(
        f"""
        SELECT s.id, s.space_id, s.name, s.kind, s.pages, sp.name AS space,
               j.started_at, j.finished_at, j.llm_calls, j.llm_cached, j.input_tokens, j.output_tokens, j.llm_model
        FROM sources s
        JOIN study_spaces sp ON sp.id = s.space_id
        JOIN jobs j ON j.id = (SELECT max(id) FROM jobs WHERE source_id = s.id AND kind = 'ingest_source'
                               AND status = 'done')
        WHERE s.status = 'ready' {where}
        ORDER BY s.created_at
        """,
        params,
    ).fetchall()
    builds = {
        r["space_id"]: r
        for r in conn.execute(
            """
            SELECT j.* FROM jobs j WHERE j.kind = 'build_graph' AND j.status = 'done'
              AND j.id = (SELECT max(id) FROM jobs WHERE space_id = j.space_id AND kind = 'build_graph'
                          AND status = 'done')
            """
        ).fetchall()
    }
    rows = []
    for s in sources:
        b = builds.get(s["space_id"])
        rows.append(
            IngestRow(
                space=s["space"],
                source=s["name"],
                kind=s["kind"],
                pages=s["pages"] or 0,
                seconds=_seconds(s["started_at"], s["finished_at"])
                + (_seconds(b["started_at"], b["finished_at"]) if b else 0),
                llm_calls=s["llm_calls"] + (b["llm_calls"] if b else 0),
                llm_cached=s["llm_cached"] + (b["llm_cached"] if b else 0),
                input_tokens=s["input_tokens"] + (b["input_tokens"] if b else 0),
                output_tokens=s["output_tokens"] + (b["output_tokens"] if b else 0),
                model=s["llm_model"] or "",
            )
        )
    return rows
