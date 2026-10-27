from core.ingest.prereqs import validate_prereqs
from core.ingest.schema import Prereq

NAMES = {"Relational Model", "SQL", "Joins", "Normalization"}


def _pairs(edges: list[Prereq]) -> list[tuple[str, str]]:
    return [(e.topic, e.requires) for e in edges]


def test_drops_unknown_self_and_duplicate_edges():
    edges = [
        Prereq(topic="SQL", requires="Relational Model"),
        Prereq(topic="SQL", requires="Relational Model"),
        Prereq(topic="SQL", requires="SQL"),
        Prereq(topic="Joins", requires="Set Theory"),
    ]
    assert _pairs(validate_prereqs(edges, NAMES)) == [("SQL", "Relational Model")]


def test_drops_edge_that_would_close_a_cycle():
    edges = [
        Prereq(topic="Joins", requires="SQL"),
        Prereq(topic="SQL", requires="Relational Model"),
        Prereq(topic="Relational Model", requires="Joins"),
    ]
    assert _pairs(validate_prereqs(edges, NAMES)) == [("Joins", "SQL"), ("SQL", "Relational Model")]
