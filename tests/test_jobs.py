import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import timedelta
from typing import Any

import pytest

from app.settings import Settings
from core.ingest.schema import PrereqsOut, SpaceGraph, TopicsOut, UnitsOut
from core.spaces import StudySpace
from core.storage import sqlite
from core.storage.files import FileStore
from core.storage.jobs import SqliteJobQueue
from core.storage.sources import Source, SqliteSourceRepository
from core.storage.spaces import SqliteStudySpaceRepository
from tests.conftest import FakeLLM
from workers import tasks
from workers.run import run_one
from workers.tasks import Context


@pytest.fixture
def conn(settings: Settings) -> Iterator[sqlite3.Connection]:
    with closing(sqlite.connect(settings.sqlite_path)) as c:
        sqlite.migrate(c)
        yield c


@pytest.fixture
def space(conn: sqlite3.Connection) -> StudySpace:
    s = StudySpace.new("DBMS")
    SqliteStudySpaceRepository(conn).add(s)
    return s


def test_queue_claims_each_job_once_in_order(conn: sqlite3.Connection, space: StudySpace) -> None:
    q = SqliteJobQueue(conn)
    first = q.enqueue("build_graph", space.id)
    second = q.enqueue("flashcards", space.id, payload={"topic_id": "t"})
    a, b = q.claim(), q.claim()
    assert (a and a.id, b and b.id) == (first, second)
    assert b is not None and b.payload == {"topic_id": "t"}
    assert q.claim() is None
    q.finish(first or 0)
    done = q.get(first or 0)
    assert done is not None and done.status == "done"


def test_dedupe_skips_identical_queued_job(conn: sqlite3.Connection, space: StudySpace) -> None:
    q = SqliteJobQueue(conn)
    assert q.enqueue("build_graph", space.id, dedupe=True) is not None
    assert q.enqueue("build_graph", space.id, dedupe=True) is None
    q.claim()  # once it's running, a new build may be queued (sources may have changed since it started)
    assert q.enqueue("build_graph", space.id, dedupe=True) is not None


def test_stale_running_jobs_are_requeued(conn: sqlite3.Connection, space: StudySpace) -> None:
    q = SqliteJobQueue(conn)
    job_id = q.enqueue("build_graph", space.id)
    q.claim()
    assert q.requeue_stale(timedelta(minutes=10)) == 0
    conn.execute("UPDATE jobs SET heartbeat_at = '2000-01-01T00:00:00.000000+00:00'")
    assert q.requeue_stale(timedelta(minutes=10)) == 1
    assert (q.get(job_id or 0) or pytest.fail()).status == "queued"


def test_deleting_a_space_cascades(conn: sqlite3.Connection, space: StudySpace) -> None:
    SqliteSourceRepository(conn).add(Source.new(space.id, "text", "notes.md"))
    SqliteJobQueue(conn).enqueue("build_graph", space.id)
    SqliteStudySpaceRepository(conn).delete(space.id)
    assert conn.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def _llm(fake: FakeLLM) -> None:
    fake.replies[TopicsOut] = lambda prompt: TopicsOut.model_validate(
        {"topics": [{"name": "Relational Model", "summary": "Tables."}, {"name": "SQL", "summary": "Queries."}]}
    )
    fake.replies[UnitsOut] = lambda prompt: UnitsOut.model_validate(
        {"units": [{"name": "Foundations", "topics": ["Relational Model", "SQL"]}]}
    )
    fake.replies[PrereqsOut] = lambda prompt: PrereqsOut.model_validate(
        {"edges": [{"topic": "SQL", "requires": "Relational Model", "confidence": 0.9}]}
    )


def test_worker_ingests_a_source_then_builds_the_graph(
    conn: sqlite3.Connection, space: StudySpace, settings: Settings, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    _llm(fake_llm)
    written: list[SpaceGraph] = []
    monkeypatch.setattr(tasks, "write_space_graph", lambda graph, driver: written.append(graph))
    files = FileStore(settings.data_dir)
    source = Source.new(space.id, "text", "notes.md")
    path = files.save_upload(space.id, source.id, ".txt", b"# Relational model\nTables and keys.\n# SQL\nSELECT.")
    SqliteSourceRepository(conn).add(source.model_copy(update={"storage_path": str(path)}))
    queue = SqliteJobQueue(conn)
    queue.enqueue("ingest_source", space.id, source.id)

    ctx = Context(settings=settings, conn=conn, driver=Any)  # type: ignore[arg-type]
    assert run_one(ctx, queue)  # ingest
    done = SqliteSourceRepository(conn).get(source.id)
    assert done is not None and (done.status, done.pages, done.progress) == ("ready", 2, 1.0)
    assert run_one(ctx, queue)  # build_graph, queued by the ingest
    assert not run_one(ctx, queue)

    [graph] = written
    assert [t.name for t in graph.topics] == ["Relational Model", "SQL"]
    assert [(p.topic, p.requires) for p in graph.prereqs] == [("SQL", "Relational Model")]
    assert (SqliteStudySpaceRepository(conn).get(space.id) or space).graph_status == "ready"
    assert (settings.cache_dir / f"{space.id}.graph.json").exists()


def test_failed_source_records_a_readable_error(
    conn: sqlite3.Connection, space: StudySpace, settings: Settings, fake_llm: FakeLLM
) -> None:
    files = FileStore(settings.data_dir)
    source = Source.new(space.id, "text", "empty.md")
    path = files.save_upload(space.id, source.id, ".txt", b"   \n")
    SqliteSourceRepository(conn).add(source.model_copy(update={"storage_path": str(path)}))
    queue = SqliteJobQueue(conn)
    job_id = queue.enqueue("ingest_source", space.id, source.id)
    run_one(Context(settings=settings, conn=conn, driver=Any), queue)  # type: ignore[arg-type]
    failed = SqliteSourceRepository(conn).get(source.id)
    assert failed is not None and (failed.status, failed.error) == ("failed", "no text found in this source")
    assert (queue.get(job_id or 0) or pytest.fail()).status == "failed"
    assert queue.claim() is None  # no graph rebuild for a failed source


def test_page_limit(conn: sqlite3.Connection, space: StudySpace, settings: Settings, fake_llm: FakeLLM) -> None:
    ctx_settings = settings.model_copy(update={"max_pages_per_space": 1})
    files = FileStore(settings.data_dir)
    source = Source.new(space.id, "text", "long.md")
    path = files.save_upload(space.id, source.id, ".txt", b"# A\none\n# B\ntwo")
    SqliteSourceRepository(conn).add(source.model_copy(update={"storage_path": str(path)}))
    queue = SqliteJobQueue(conn)
    queue.enqueue("ingest_source", space.id, source.id)
    run_one(Context(settings=ctx_settings, conn=conn, driver=Any), queue)  # type: ignore[arg-type]
    failed = SqliteSourceRepository(conn).get(source.id)
    assert failed is not None and failed.error is not None and "limited to 1 pages" in failed.error
