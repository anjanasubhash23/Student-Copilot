"""Job handlers. Each is idempotent: running a job twice gives the same result as running it once."""

import hashlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from neo4j import Driver

from app.settings import Settings
from core.graph.writer import delete_space_graph, write_space_graph
from core.ingest.pipeline import build_space_graph, extract_source
from core.ingest.schema import Page
from core.llm import unavailable_reason
from core.sources import SourceError, load_file, load_web, load_youtube
from core.storage.files import FileStore
from core.storage.jobs import Job, SqliteJobQueue
from core.storage.sources import Source, SqliteSourceRepository
from core.storage.spaces import SqliteStudySpaceRepository

log = logging.getLogger(__name__)


class JobError(Exception):
    """A failure whose message is meant for the user (shown as the source's or the graph's error)."""


@dataclass
class Context:
    settings: Settings
    conn: sqlite3.Connection
    driver: Driver

    @property
    def files(self) -> FileStore:
        return FileStore(self.settings.data_dir)


def run_job(ctx: Context, job: Job) -> None:
    match job.kind:
        case "ingest_source":
            ingest_source(ctx, job)
        case "build_graph":
            build_graph(ctx, job)
        case "flashcards":
            from core.questions.flashcards import ensure_flashcards

            ensure_flashcards(ctx.conn, ctx.driver, job.space_id, str(job.payload["topic_id"]))


def _load_pages(ctx: Context, src: Source, sources: SqliteSourceRepository) -> list[Page]:
    if src.kind in ("web", "youtube"):
        assert src.uri is not None
        if src.kind == "youtube":
            return load_youtube(src.uri)
        pages, title = load_web(src.uri, ctx.settings.max_fetch_mb * 1_000_000)
        sources.update(src.id, name=title[:200])
        return pages
    assert src.storage_path is not None
    return load_file(src.kind, Path(src.storage_path), ctx.settings.ocr_lang)


def ingest_source(ctx: Context, job: Job) -> None:
    sources, queue = SqliteSourceRepository(ctx.conn), SqliteJobQueue(ctx.conn)
    src = sources.get(job.source_id or "")
    if src is None:
        return  # deleted while queued

    def stage(name: str, progress: float = 0.0) -> None:
        sources.update(src.id, status="processing", stage=name, progress=progress)
        queue.progress(job.id, name, progress)

    try:
        stage("reading")
        pages = _load_pages(ctx, src, sources)
        if not any(p.text.strip() for p in pages):
            raise JobError("no text found in this source")
        if src.kind in ("web", "youtube"):
            digest = hashlib.sha256("\n".join(p.text for p in pages).encode()).hexdigest()
            sources.update(src.id, content_hash=digest)
        used = sum(s.pages or 0 for s in sources.list_for_space(src.space_id) if s.status == "ready" and s.id != src.id)
        if used + len(pages) > ctx.settings.max_pages_per_space:
            raise JobError(
                f"this source has {len(pages)} pages; the space is limited to {ctx.settings.max_pages_per_space} "
                f"pages and already has {used}"
            )
        stage("finding topics")
        ref = (sources.get(src.id) or src).ref
        extraction = extract_source(ref, pages, on_progress=lambda done: stage("finding topics", done))
        ctx.files.save_extraction(src.space_id, extraction)
    except (JobError, *SourceError) as exc:
        sources.update(src.id, status="failed", stage=None, error=str(exc))
        raise JobError(str(exc)) from exc
    except Exception as exc:
        reason = unavailable_reason(exc)
        sources.update(src.id, status="failed", stage=None, error=reason or f"ingestion failed: {type(exc).__name__}")
        if reason:
            raise JobError(reason) from exc
        raise
    sources.update(src.id, status="ready", stage="ready", progress=1.0, pages=len(pages), error=None)
    queue.enqueue("build_graph", src.space_id, dedupe=True)


def build_graph(ctx: Context, job: Job) -> None:
    spaces, sources, queue = (
        SqliteStudySpaceRepository(ctx.conn),
        SqliteSourceRepository(ctx.conn),
        SqliteJobQueue(ctx.conn),
    )
    if spaces.get(job.space_id) is None:
        return
    spaces.set_graph_status(job.space_id, "building")
    try:
        extractions = [
            e
            for s in sources.list_for_space(job.space_id)
            if s.status == "ready" and (e := ctx.files.load_extraction(job.space_id, s.id)) is not None
        ]
        if not extractions:
            delete_space_graph(job.space_id, ctx.driver)
            spaces.set_graph_status(job.space_id, "empty")
            return
        graph = build_space_graph(job.space_id, extractions, on_stage=lambda name: queue.progress(job.id, name))
        queue.progress(job.id, "writing graph")
        write_space_graph(graph, ctx.driver)
        out = ctx.settings.cache_dir / f"{job.space_id}.graph.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(graph.model_dump_json(indent=2))
    except Exception as exc:
        reason = unavailable_reason(exc)
        spaces.set_graph_status(
            job.space_id, "failed", reason or f"building the topic map failed: {type(exc).__name__}"
        )
        if reason:
            raise JobError(reason) from exc
        raise
    spaces.set_graph_status(job.space_id, "ready")
