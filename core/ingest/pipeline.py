from pathlib import Path

from core.graph import write_course_graph
from core.ingest.extract import extract_prereqs, extract_topics
from core.ingest.pdf import chunk_pages, read_pages


def ingest_pdf(course: str, path: Path) -> dict:
    chunks = chunk_pages(read_pages(path))
    topics = extract_topics(chunks)
    prereqs = extract_prereqs(topics)
    write_course_graph(course, topics, prereqs)
    return {"chunks": len(chunks), "topics": len(topics), "prereqs": len(prereqs)}
