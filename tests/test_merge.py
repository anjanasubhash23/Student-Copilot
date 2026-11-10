from core.ingest.merge import merge_topics, normalize
from core.ingest.schema import Topic


def test_normalize():
    assert normalize("B+ Trees") == normalize("b+ tree")
    assert normalize("Structured Query Language (SQL)") == "structured query language"
    assert normalize("Access Methods") == normalize("access method")


def test_merges_duplicates_and_unions_chunks():
    merged = merge_topics(
        [
            Topic(name="B+ Tree", summary="Index.", chunks=["s:1"], first_seen=1),
            Topic(name="Third Normal Form", summary="3NF.", chunks=["s:2"], first_seen=2),
            Topic(name="B+ Trees", summary="Balanced tree index.", chunks=["s:3", "s:1"], first_seen=3),
        ]
    )
    assert [t.name for t in merged] == ["B+ Tree", "Third Normal Form"]
    assert merged[0].chunks == ["s:1", "s:3"]
    assert merged[0].first_seen == 1
    assert merged[0].aliases == ["B+ Trees"]
    assert merged[0].summary == "Balanced tree index."


def test_keeps_distinct_normal_forms_apart():
    names = ["First Normal Form", "Second Normal Form", "Third Normal Form", "Boyce-Codd Normal Form"]
    assert len(merge_topics([Topic(name=n, summary="") for n in names])) == 4
