import sqlite3
from contextlib import closing
from pathlib import Path

from core.evaluation.labels import edge_precision, merge_scores, question_validity, read_csv, sample_merges, verdict
from core.evaluation.report import ingest_report
from core.ingest.schema import ExtractedBy, SpaceGraph, Topic
from core.spaces import StudySpace
from core.storage import sqlite
from core.storage.jobs import SqliteJobQueue
from core.storage.sources import Source, SqliteSourceRepository
from core.storage.spaces import SqliteStudySpaceRepository


def test_verdicts() -> None:
    assert [verdict(v) for v in ["y", " YES ", "n", "", "maybe", None]] == [True, True, False, None, None, None]


def test_edge_precision_skips_unlabelled_rows() -> None:
    rows = read_csv("requires,topic,reason,confidence,correct\nA,B,,1,y\nB,C,,1,n\nC,D,,1,\nD,E,,1,yes\n")
    p = edge_precision(rows)
    assert (p.hits, p.total, p.value) == (2, 3, 2 / 3)


def test_merge_precision_and_recall() -> None:
    rows = read_csv(
        "a,b,predicted_same,same\n"
        "3NF,Third Normal Form,y,y\n"  # right merge
        "B Tree,B+ Tree,y,n\n"  # wrong merge
        "SQL Join,SQL Joins,n,y\n"  # missed duplicate
        "1NF,2NF,n,n\n"
    )
    precision, recall = merge_scores(rows)
    assert (precision.hits, precision.total) == (1, 2)
    assert (recall.hits, recall.total) == (1, 2)


def test_question_validity_and_agreement() -> None:
    rows = read_csv(
        "id,topic,type,status,stem,options,answer,source_excerpt,correct\n"
        "1,t,mcq,valid,?,[],a,,y\n"
        "2,t,mcq,valid,?,[],a,,n\n"
        "3,t,mcq,rejected,?,[],a,,n\n"
    )
    validity, agreement = question_validity(rows)
    assert (validity.hits, validity.total) == (1, 2)
    assert (agreement.hits, agreement.total) == (2, 3)


def test_sample_merges_includes_merged_and_near_miss_pairs() -> None:
    graph = SpaceGraph(
        space_id="s",
        sources=[],
        chunks=[],
        topics=[
            Topic(name="Third Normal Form", summary="", aliases=["3NF"]),
            Topic(name="Second Normal Form", summary=""),
            Topic(name="Hashing", summary=""),
        ],
        units=[],
        prereqs=[],
        extracted_by=ExtractedBy(model="m", prompts={}),
    )
    rows = sample_merges(graph)
    assert {"a": "Third Normal Form", "b": "3NF", "predicted_same": "y", "same": ""} in rows
    near = [(r["a"], r["b"]) for r in rows if r["predicted_same"] == "n"]
    assert ("Third Normal Form", "Second Normal Form") in near
    assert all("Hashing" not in pair for pair in near)


def test_ingest_report_adds_the_graph_build(tmp_path: Path) -> None:
    with closing(sqlite.connect(tmp_path / "app.db")) as conn:
        sqlite.migrate(conn)
        space = StudySpace.new("DBMS")
        SqliteStudySpaceRepository(conn).add(space)
        source = Source.new(space.id, "pdf", "notes.pdf")
        SqliteSourceRepository(conn).add(source)
        SqliteSourceRepository(conn).update(source.id, status="ready", pages=50)
        q = SqliteJobQueue(conn)
        ingest = q.enqueue("ingest_source", space.id, source.id)
        build = q.enqueue("build_graph", space.id)
        for job_id, start, end, calls in [(ingest, "10:00:00", "10:02:00", 12), (build, "10:02:00", "10:03:30", 2)]:
            conn.execute(
                "UPDATE jobs SET status='done', started_at=?, finished_at=?, llm_calls=?, llm_model='m' WHERE id=?",
                (f"2026-11-10T{start}.000000+00:00", f"2026-11-10T{end}.000000+00:00", calls, job_id),
            )
        conn.commit()
        [row] = ingest_report(conn)
    assert (row.source, row.pages, row.seconds, row.llm_calls) == ("notes.pdf", 50, 210.0, 14)
    assert row.seconds_per_100_pages == 420.0


def test_report_on_empty_db(tmp_path: Path) -> None:
    with closing(sqlite.connect(tmp_path / "app.db")) as conn:
        sqlite.migrate(conn)
        assert ingest_report(conn) == []
    assert isinstance(conn, sqlite3.Connection)
