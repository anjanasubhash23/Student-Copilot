from core.graph.ids import assign_ids, slugify
from core.graph.writer import rows
from core.ingest.schema import Chunk, ExtractedBy, Prereq, SourceRef, SpaceGraph, Topic, Unit


def test_slugify() -> None:
    assert slugify("Third Normal Form (3NF)") == "third-normal-form-3nf"
    assert slugify("B+ Tree") == "b-plus-tree"
    assert slugify("B Tree") == "b-tree"
    assert slugify("Café Schéma") == "cafe-schema"
    assert slugify("???") == "untitled"


def test_assign_ids_is_space_prefixed_and_unique() -> None:
    ids = assign_ids("s1", ["SQL Joins", "SQL: Joins", "Normalization", "SQL Joins"])
    assert ids == {"SQL Joins": "s1:sql-joins", "SQL: Joins": "s1:sql-joins-2", "Normalization": "s1:normalization"}


def _graph() -> SpaceGraph:
    return SpaceGraph(
        space_id="s1",
        sources=[SourceRef(id="abc", name="dbms.pdf", kind="pdf"), SourceRef(id="yt", name="Joins", kind="youtube")],
        chunks=[
            Chunk(id=0, source_id="abc", page_start=1, page_end=2, text="..."),
            Chunk(id=0, source_id="yt", page_start=1, page_end=1, timestamp=60.0, text="..."),
        ],
        topics=[
            Topic(name="Relational Model", summary="Tables.", chunks=["abc:0"], first_seen=0),
            Topic(name="SQL", summary="Queries.", chunks=["abc:0", "yt:0"], first_seen=0),
        ],
        units=[Unit(name="Foundations", order=1, topics=["Relational Model", "SQL"])],
        prereqs=[Prereq(topic="SQL", requires="Relational Model", reason="queries tables", confidence=0.9)],
        extracted_by=ExtractedBy(model="ollama/llama3.1:8b", prompts={"topics": "t1", "units": "u1", "prereqs": "p1"}),
    )


def test_rows_link_everything_by_id() -> None:
    r = rows(_graph())
    assert r["space_id"] == "s1"
    assert r["units"] == [{"id": "s1:foundations", "name": "Foundations", "order": 1}]
    assert [t["id"] for t in r["topics"]] == ["s1:relational-model", "s1:sql"]
    assert r["topics"][0]["extracted_by"] == "ollama/llama3.1:8b topics@t1"
    assert [c["id"] for c in r["chunks"]] == ["s1:abc:0", "s1:yt:0"]
    assert [(c["source"], c["kind"], c["position"], c["timestamp"]) for c in r["chunks"]] == [
        ("dbms.pdf", "pdf", 0, None),
        ("Joins", "youtube", 1, 60.0),
    ]
    assert r["has_topic"] == [
        {"unit": "s1:foundations", "topic": "s1:relational-model", "position": 1},
        {"unit": "s1:foundations", "topic": "s1:sql", "position": 2},
    ]
    assert {(a["chunk"], a["topic"]) for a in r["about"]} == {
        ("s1:abc:0", "s1:relational-model"),
        ("s1:abc:0", "s1:sql"),
        ("s1:yt:0", "s1:sql"),
    }


def test_prerequisite_edge_points_from_prerequisite_to_dependent() -> None:
    [edge] = rows(_graph())["prereqs"]
    assert (edge["from"], edge["to"]) == ("s1:relational-model", "s1:sql")
    assert edge["confidence"] == 0.9
    assert edge["extracted_by"] == "ollama/llama3.1:8b prereqs@p1"


def test_graph_json_round_trips() -> None:
    g = _graph()
    assert SpaceGraph.model_validate_json(g.model_dump_json()) == g
