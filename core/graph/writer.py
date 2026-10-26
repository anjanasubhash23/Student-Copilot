"""Write a CourseGraph to Neo4j, replacing any previous ingest of the same course.

(:Course)-[:HAS_UNIT]->(:Unit)<-[:IN_UNIT]-(:Topic)-[:REQUIRES]->(:Topic)
"""

from neo4j import ManagedTransaction

from core.graph.client import get_driver
from core.ingest.schema import CourseGraph

CONSTRAINTS = [
    "CREATE CONSTRAINT course_id IF NOT EXISTS FOR (c:Course) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT topic_key IF NOT EXISTS FOR (t:Topic) REQUIRE (t.course, t.name) IS UNIQUE",
]


def write_course_graph(graph: CourseGraph) -> None:
    with get_driver().session() as session:
        for stmt in CONSTRAINTS:
            session.run(stmt)
        session.execute_write(_write, graph)


def _write(tx: ManagedTransaction, g: CourseGraph) -> None:
    course = g.course
    tx.run(
        """
        MATCH (n) WHERE (n:Course AND n.id = $course) OR ((n:Unit OR n:Topic) AND n.course = $course)
        DETACH DELETE n
        """,
        course=course,
    )
    tx.run("CREATE (:Course {id: $course, source: $source})", course=course, source=g.source)
    tx.run(
        """
        MATCH (c:Course {id: $course})
        UNWIND $units AS u
        CREATE (c)-[:HAS_UNIT]->(:Unit {course: $course, name: u.name, order: u.order})
        """,
        course=course,
        units=[u.model_dump(include={"name", "order"}) for u in g.units],
    )
    tx.run(
        """
        UNWIND $topics AS t
        CREATE (:Topic {course: $course, name: t.name, summary: t.summary, pages: t.pages, aliases: t.aliases})
        """,
        course=course,
        topics=[t.model_dump() for t in g.topics],
    )
    tx.run(
        """
        UNWIND $members AS m
        MATCH (u:Unit {course: $course, name: m.unit})
        MATCH (t:Topic {course: $course, name: m.topic})
        CREATE (t)-[:IN_UNIT {position: m.position}]->(u)
        """,
        course=course,
        members=[
            {"unit": u.name, "topic": name, "position": i}
            for u in g.units
            for i, name in enumerate(u.topics, start=1)
        ],
    )
    tx.run(
        """
        UNWIND $edges AS e
        MATCH (a:Topic {course: $course, name: e.topic})
        MATCH (b:Topic {course: $course, name: e.requires})
        CREATE (a)-[:REQUIRES {reason: e.reason}]->(b)
        """,
        course=course,
        edges=[p.model_dump() for p in g.prereqs],
    )
