import hashlib
import logging
from pathlib import Path

from core.ingest.chunk import chunk_pages
from core.ingest.clean import clean_pages
from core.ingest.merge import merge_topics
from core.ingest.prereqs import extract_prereqs
from core.ingest.schema import ExtractedBy, SpaceGraph
from core.ingest.topics import extract_topics
from core.ingest.units import group_units
from core.llm import model_label, prompt_version
from core.sources import load_pdf

log = logging.getLogger(__name__)

PROMPTS = ("topics", "units", "prereqs")


def source_id(path: Path) -> str:
    """Content hash, so the same file gets the same id wherever it lives or whatever it's called."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def build_space_graph(space_id: str, path: Path) -> SpaceGraph:
    # Captured before any LLM call, so the versions match the prompts that were actually used.
    extracted_by = ExtractedBy(model=model_label(), prompts={name: prompt_version(name) for name in PROMPTS})

    pages = clean_pages(load_pdf(path))
    chunks = chunk_pages(pages)
    log.info("%d pages → %d chunks", len(pages), len(chunks))

    raw = extract_topics(chunks)
    topics = merge_topics(raw)
    log.info("%d topics extracted → %d after merge", len(raw), len(topics))

    units = group_units(topics)
    prereqs = extract_prereqs(topics, units)
    log.info("%d units, %d prerequisite edges", len(units), len(prereqs))

    return SpaceGraph(
        space_id=space_id,
        source_id=source_id(path),
        source=path.name,
        chunks=chunks,
        topics=topics,
        units=units,
        prereqs=prereqs,
        extracted_by=extracted_by,
    )
