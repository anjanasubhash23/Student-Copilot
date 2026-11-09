"""Read queries over a space's topic graph.

Every query takes `space_id` and filters every node it matches on it; tests/test_graph_scoping.py
fails if one doesn't.
"""

from typing import Any

from neo4j import Driver

from core.graph.client import get_driver


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
            RETURN t.id AS id, t.name AS name, t.summary AS summary, t.pages AS pages,
                   requires, collect(d.name) AS required_by
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


def get_graph(space_id: str, driver: Driver | None = None) -> dict[str, Any]:
    """Units, topics and prerequisite edges: everything needed to draw the space's map."""
    with (driver or get_driver()).session() as session:
        topics = session.run(
            """
            MATCH (t:Topic {space_id: $space_id})
            OPTIONAL MATCH (u:Unit {space_id: $space_id})-[:HAS_TOPIC]->(t)
            RETURN t.id AS id, t.name AS name, t.summary AS summary, u.id AS unit
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
    return {"units": get_units(space_id, driver), "topics": topics, "edges": edges}
