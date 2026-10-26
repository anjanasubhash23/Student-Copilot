from core.graph.client import get_driver


def get_units(course: str) -> list[dict]:
    with get_driver().session() as session:
        result = session.run(
            """
            MATCH (:Course {id: $course})-[:HAS_UNIT]->(u:Unit)<-[r:IN_UNIT]-(t:Topic)
            WITH u, t ORDER BY r.position
            RETURN u.name AS name, u.order AS order, collect(t.name) AS topics
            ORDER BY order
            """,
            course=course,
        )
        return [r.data() for r in result]


def get_topic(course: str, name: str) -> dict | None:
    with get_driver().session() as session:
        record = session.run(
            """
            MATCH (t:Topic {course: $course, name: $name})
            OPTIONAL MATCH (t)-[:REQUIRES]->(p:Topic)
            WITH t, collect(p.name) AS requires
            OPTIONAL MATCH (d:Topic)-[:REQUIRES]->(t)
            RETURN t.name AS name, t.summary AS summary, t.pages AS pages,
                   requires, collect(d.name) AS required_by
            """,
            course=course,
            name=name,
        ).single()
        return record.data() if record else None


def learning_path(course: str, target: str) -> list[str]:
    """Every transitive prerequisite of `target`, deepest first, ending with `target`."""
    with get_driver().session() as session:
        result = session.run(
            """
            MATCH path = (:Topic {course: $course, name: $target})-[:REQUIRES*]->(p:Topic)
            RETURN p.name AS name, max(length(path)) AS depth
            ORDER BY depth DESC, name
            """,
            course=course,
            target=target,
        )
        return [r["name"] for r in result] + [target]
