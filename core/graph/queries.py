"""Read queries over a space's topic graph.

Every query takes `space_id` and filters every node it matches on it; tests/test_graph_scoping.py
fails if one doesn't.
"""

import re
from typing import Any

from neo4j import Driver

from core.graph.client import get_driver
from core.graph.space_map import SpaceMap, TopicInfo


def get_units(space_id: str, driver: Driver | None = None) -> list[dict[str, Any]]:
    """Units in order, each with its topic names in teaching order."""
    with (driver or get_driver()).session() as session:
        result = session.run(
            """
            MATCH (u:Unit {space_id: $space_id})-[r:HAS_TOPIC]->(t:Topic {space_id: $space_id})
            WITH u, t ORDER BY r.position
            RETURN u.id AS id, u.name AS name, u.order AS order, collect(t.name) AS topics
            ORDER BY order
            """,
            space_id=space_id,
        )
        return [r.data() for r in result]


def get_topic(space_id: str, name: str, driver: Driver | None = None) -> dict[str, Any] | None:
    """A topic with its direct prerequisites and the topics that build on it."""
    with (driver or get_driver()).session() as session:
        record = session.run(
            """
            MATCH (t:Topic {space_id: $space_id, name: $name})
            OPTIONAL MATCH (p:Topic {space_id: $space_id})-[:PREREQUISITE_OF]->(t)
            WITH t, collect(p.name) AS requires
            OPTIONAL MATCH (t)-[:PREREQUISITE_OF]->(d:Topic {space_id: $space_id})
            RETURN t.id AS id, t.name AS name, t.summary AS summary, requires, collect(d.name) AS required_by
            """,
            space_id=space_id,
            name=name,
        ).single()
        return record.data() if record else None


def learning_path(space_id: str, target: str, driver: Driver | None = None) -> list[str]:
    """Every transitive prerequisite of `target`, deepest first, ending with `target`."""
    with (driver or get_driver()).session() as session:
        result = session.run(
            """
            MATCH path = (p:Topic {space_id: $space_id})
                         -[:PREREQUISITE_OF*]->(:Topic {space_id: $space_id, name: $target})
            RETURN p.name AS name, max(length(path)) AS depth
            ORDER BY depth DESC, name
            """,
            space_id=space_id,
            target=target,
        )
        return [r["name"] for r in result] + [target]


def get_space_map(space_id: str, driver: Driver | None = None) -> SpaceMap:
    """Units, topics and prerequisite edges: what the learning loop and the map view work from."""
    with (driver or get_driver()).session() as session:
        topics = session.run(
            """
            MATCH (t:Topic {space_id: $space_id})
            OPTIONAL MATCH (u:Unit {space_id: $space_id})-[r:HAS_TOPIC]->(t)
            RETURN t.id AS id, t.name AS name, t.summary AS summary, t.first_seen AS first_seen,
                   u.id AS unit_id, u.name AS unit, u.order AS unit_order, r.position AS position
            ORDER BY t.first_seen, t.name
            """,
            space_id=space_id,
        ).data()
        edges = session.run(
            """
            MATCH (a:Topic {space_id: $space_id})-[e:PREREQUISITE_OF]->(b:Topic {space_id: $space_id})
            RETURN a.id AS source, b.id AS target, e.confidence AS confidence
            """,
            space_id=space_id,
        ).data()
    return SpaceMap.build(
        [
            TopicInfo(
                id=t["id"],
                name=t["name"],
                summary=t["summary"] or "",
                first_seen=t["first_seen"] or 0,
                unit_id=t["unit_id"],
                unit=t["unit"],
                unit_order=t["unit_order"] or 0,
                position=t["position"] or 0,
            )
            for t in topics
        ],
        [(e["source"], e["target"], e["confidence"] if e["confidence"] is not None else 1.0) for e in edges],
    )


CHUNK_FIELDS = """c.id AS id, c.text AS text, c.source AS source, c.kind AS kind,
                  c.page_start AS page_start, c.page_end AS page_end, c.timestamp AS timestamp"""


def topic_chunks(space_id: str, topic_id: str, limit: int = 3, driver: Driver | None = None) -> list[dict[str, Any]]:
    """Chunks that teach a topic, in the order they appear in the material."""
    with (driver or get_driver()).session() as session:
        return session.run(
            f"""
            MATCH (c:Chunk {{space_id: $space_id}})-[:ABOUT]->(:Topic {{space_id: $space_id, id: $topic_id}})
            RETURN {CHUNK_FIELDS}
            ORDER BY c.position
            LIMIT $limit
            """,
            space_id=space_id,
            topic_id=topic_id,
            limit=limit,
        ).data()


def get_chunks(space_id: str, ids: list[str], driver: Driver | None = None) -> list[dict[str, Any]]:
    with (driver or get_driver()).session() as session:
        return session.run(
            f"""
            MATCH (c:Chunk {{space_id: $space_id}}) WHERE c.id IN $ids
            RETURN {CHUNK_FIELDS}
            """,
            space_id=space_id,
            ids=ids,
        ).data()


STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "explain",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "or",
        "please",
        "the",
        "this",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    ]
)


def lucene_query(text: str) -> str:
    """Plain words OR-ed together. User text never reaches Lucene's query syntax (no operators, no wildcards)."""
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]
    return " ".join(dict.fromkeys(words))


def search_topics(space_id: str, text: str, limit: int = 3, driver: Driver | None = None) -> list[dict[str, Any]]:
    terms = lucene_query(text)
    if not terms:
        return []
    with (driver or get_driver()).session() as session:
        return session.run(
            """
            CALL db.index.fulltext.queryNodes('topic_text', $terms) YIELD node, score
            WITH node, score WHERE node.space_id = $space_id
            RETURN node.id AS id, node.name AS name, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            space_id=space_id,
            terms=terms,
            limit=limit,
        ).data()


def search_chunks(
    space_id: str, text: str, topic_ids: list[str] | None = None, limit: int = 3, driver: Driver | None = None
) -> list[dict[str, Any]]:
    """Best-matching chunks; with `topic_ids`, only chunks about one of those topics. Each row has its topic ids."""
    terms = lucene_query(text)
    if not terms:
        return []
    with (driver or get_driver()).session() as session:
        return session.run(
            f"""
            CALL db.index.fulltext.queryNodes('chunk_text', $terms) YIELD node AS c, score
            WITH c, score WHERE c.space_id = $space_id
            MATCH (c)-[:ABOUT]->(t:Topic {{space_id: $space_id}})
            WITH c, score, collect(t.id) AS topics
            WHERE $topic_ids IS NULL OR any(id IN topics WHERE id IN $topic_ids)
            RETURN {CHUNK_FIELDS}, topics, score
            ORDER BY score DESC
            LIMIT $limit
            """,
            space_id=space_id,
            terms=terms,
            topic_ids=topic_ids,
            limit=limit,
        ).data()
