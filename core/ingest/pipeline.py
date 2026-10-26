import logging
from pathlib import Path

from core.ingest.chunk import chunk_pages
from core.ingest.clean import clean_pages
from core.ingest.merge import merge_topics
from core.ingest.prereqs import extract_prereqs
from core.ingest.schema import CourseGraph
from core.ingest.topics import extract_topics
from core.ingest.units import group_units
from core.sources import load_pdf

log = logging.getLogger(__name__)


def build_course_graph(course: str, path: Path) -> CourseGraph:
    pages = clean_pages(load_pdf(path))
    chunks = chunk_pages(pages)
    log.info("%d pages → %d chunks", len(pages), len(chunks))

    raw = extract_topics(chunks)
    topics = merge_topics(raw)
    log.info("%d topics extracted → %d after merge", len(raw), len(topics))

    units = group_units(topics)
    prereqs = extract_prereqs(topics, units)
    log.info("%d units, %d prerequisite edges", len(units), len(prereqs))

    return CourseGraph(course=course, source=path.name, topics=topics, units=units, prereqs=prereqs)
