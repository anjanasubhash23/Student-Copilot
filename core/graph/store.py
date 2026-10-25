from functools import lru_cache

from neo4j import Driver, GraphDatabase

from core.config import get_settings


@lru_cache
def get_driver() -> Driver:
    s = get_settings()
    return GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))


def write_course_graph(course: str, topics, prereqs) -> None:
    with get_driver().session() as session:
        session.run("MERGE (:Course {id: $course})", course=course)
        session.run(
            """
            UNWIND $topics AS t
            MATCH (c:Course {id: $course})
            MERGE (n:Topic {course: $course, name: t.name})
            SET n.summary = t.summary, n.pages = t.pages
            MERGE (c)-[:HAS_TOPIC]->(n)
            """,
            course=course,
            topics=[{"name": t.name, "summary": t.summary, "pages": t.pages} for t in topics],
        )
        session.run(
            """
            UNWIND $edges AS e
            MATCH (a:Topic {course: $course, name: e.topic})
            MATCH (b:Topic {course: $course, name: e.requires})
            MERGE (a)-[:REQUIRES]->(b)
            """,
            course=course,
            edges=[{"topic": p.topic, "requires": p.requires} for p in prereqs],
        )


def get_topics(course: str) -> list[dict]:
    with get_driver().session() as session:
        result = session.run(
            """
            MATCH (:Course {id: $course})-[:HAS_TOPIC]->(t:Topic)
            OPTIONAL MATCH (t)-[:REQUIRES]->(p:Topic)
            RETURN t.name AS name, t.summary AS summary, t.pages AS pages, collect(p.name) AS requires
            ORDER BY name
            """,
            course=course,
        )
        return [r.data() for r in result]
