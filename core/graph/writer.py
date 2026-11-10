"""Write a SpaceGraph to Neo4j, replacing whatever the space held before.

(:Unit)-[:HAS_TOPIC {position}]->(:Topic)
(:Chunk)-[:ABOUT]->(:Topic)
(:Topic)-[:PREREQUISITE_OF {confidence, reason, extracted_by}]->(:Topic)   learn the first, then the second

Every node carries `space_id`; one database serves all spaces. The graph is rebuilt from all of the space's
sources whenever one is added or removed; replacing it in a single transaction keeps that idempotent and
never leaves a half-written graph.
"""

from typing import Any

from neo4j import Driver, ManagedTransaction

from core.graph.client import get_driver
from core.graph.ids import assign_ids, chunk_id
from core.ingest.schema import SpaceGraph

LABELS = ("Topic", "Unit", "Chunk")

SCHEMA = [
    *(f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE" for label in LABELS),
    *(f"CREATE INDEX {label.lower()}_space IF NOT EXISTS FOR (n:{label}) ON (n.space_id)" for label in LABELS),
    # Lucene full-text indexes for explain-mode retrieval (core.graph.queries.search_*).
    "CREATE FULLTEXT INDEX topic_text IF NOT EXISTS FOR (n:Topic) ON EACH [n.name, n.summary]",
    "CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS FOR (n:Chunk) ON EACH [n.text]",
]


def ensure_schema(driver: Driver | None = None) -> None:
    with (driver or get_driver()).session() as session:
        for stmt in SCHEMA:
            session.run(stmt)


def write_space_graph(graph: SpaceGraph, driver: Driver | None = None) -> None:
    ensure_schema(driver)
    with (driver or get_driver()).session() as session:
        session.execute_write(_write, rows(graph))


def delete_space_graph(space_id: str, driver: Driver | None = None) -> None:
    with (driver or get_driver()).session() as session:
        session.execute_write(_delete, space_id)


def _delete(tx: ManagedTransaction, space_id: str) -> None:
    tx.run(
        """
        MATCH (n) WHERE n.space_id = $space_id AND (n:Topic OR n:Unit OR n:Chunk)
        DETACH DELETE n
        """,
        space_id=space_id,
    )


def rows(g: SpaceGraph) -> dict[str, Any]:
    """Flatten the graph into the parameter lists the Cypher below expects. Pure, so it's unit-tested."""
    topic_ids = assign_ids(g.space_id, [t.name for t in g.topics])
    unit_ids = assign_ids(g.space_id, [u.name for u in g.units])
    prereq_label = g.extracted_by.label("prereqs")
    topic_label = g.extracted_by.label("topics")
    sources = {s.id: s for s in g.sources}
    return {
        "space_id": g.space_id,
        "units": [{"id": unit_ids[u.name], "name": u.name, "order": u.order} for u in g.units],
        "topics": [
            {
                "id": topic_ids[t.name],
                "name": t.name,
                "summary": t.summary,
                "aliases": t.aliases,
                "first_seen": t.first_seen,
                "extracted_by": topic_label,
            }
            for t in g.topics
        ],
        "chunks": [
            {
                "id": chunk_id(g.space_id, c.source_id, c.id),
                "source_id": c.source_id,
                "source": sources[c.source_id].name,
                "kind": sources[c.source_id].kind,
                "position": i,
                "text": c.text,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "timestamp": c.timestamp,
            }
            for i, c in enumerate(g.chunks)
        ],
        "has_topic": [
            {"unit": unit_ids[u.name], "topic": topic_ids[name], "position": i}
            for u in g.units
            for i, name in enumerate(u.topics, start=1)
        ],
        "about": [{"chunk": f"{g.space_id}:{key}", "topic": topic_ids[t.name]} for t in g.topics for key in t.chunks],
        "prereqs": [
            {
                "from": topic_ids[p.requires],
                "to": topic_ids[p.topic],
                "reason": p.reason,
                "confidence": p.confidence,
                "extracted_by": prereq_label,
            }
            for p in g.prereqs
        ],
    }


def _write(tx: ManagedTransaction, r: dict[str, Any]) -> None:
    space_id = r["space_id"]
    _delete(tx, space_id)
    tx.run(
        """
        UNWIND $units AS u
        CREATE (:Unit {id: u.id, space_id: $space_id, name: u.name, order: u.order})
        """,
        space_id=space_id,
        units=r["units"],
    )
    tx.run(
        """
        UNWIND $topics AS t
        CREATE (:Topic {id: t.id, space_id: $space_id, name: t.name, summary: t.summary, aliases: t.aliases,
                        first_seen: t.first_seen, extracted_by: t.extracted_by})
        """,
        space_id=space_id,
        topics=r["topics"],
    )
    tx.run(
        """
        UNWIND $chunks AS c
        CREATE (:Chunk {id: c.id, space_id: $space_id, source_id: c.source_id, source: c.source, kind: c.kind,
                        position: c.position, text: c.text, page_start: c.page_start, page_end: c.page_end,
                        timestamp: c.timestamp})
        """,
        space_id=space_id,
        chunks=r["chunks"],
    )
    tx.run(
        """
        UNWIND $rels AS m
        MATCH (u:Unit {id: m.unit, space_id: $space_id})
        MATCH (t:Topic {id: m.topic, space_id: $space_id})
        CREATE (u)-[:HAS_TOPIC {position: m.position}]->(t)
        """,
        space_id=space_id,
        rels=r["has_topic"],
    )
    tx.run(
        """
        UNWIND $rels AS a
        MATCH (c:Chunk {id: a.chunk, space_id: $space_id})
        MATCH (t:Topic {id: a.topic, space_id: $space_id})
        CREATE (c)-[:ABOUT]->(t)
        """,
        space_id=space_id,
        rels=r["about"],
    )
    tx.run(
        """
        UNWIND $rels AS e
        MATCH (a:Topic {id: e.from, space_id: $space_id})
        MATCH (b:Topic {id: e.to, space_id: $space_id})
        CREATE (a)-[:PREREQUISITE_OF {reason: e.reason, confidence: e.confidence, extracted_by: e.extracted_by}]->(b)
        """,
        space_id=space_id,
        rels=r["prereqs"],
    )
