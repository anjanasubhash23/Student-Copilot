"""Ingest in two steps, so adding a source doesn't redo the expensive per-chunk work of the others:

1. `extract_source`: one source's pages → clean → chunks → topics per chunk (one LLM call each, cached).
2. `build_space_graph`: every source of a space → merge topics across sources → units → prerequisites.
"""

import logging
from collections.abc import Callable

from core.ingest.chunk import chunk_pages
from core.ingest.clean import clean_pages
from core.ingest.merge import merge_topics
from core.ingest.prereqs import extract_prereqs
from core.ingest.schema import ExtractedBy, Page, SourceExtraction, SourceRef, SpaceGraph
from core.ingest.topics import Progress, extract_topics
from core.ingest.units import group_units
from core.llm import model_label, prompt_version

log = logging.getLogger(__name__)

PROMPTS = ("topics", "units", "prereqs")

# Repeated headers/footers only exist in paginated material.
PAGINATED = {"pdf", "pptx"}

Stage = Callable[[str], None]


def extract_source(source: SourceRef, pages: list[Page], on_progress: Progress | None = None) -> SourceExtraction:
    if source.kind in PAGINATED:
        pages = clean_pages(pages)
    chunks = chunk_pages(pages, source_id=source.id)
    timestamps = {p.number: p.timestamp for p in pages}
    for chunk in chunks:
        chunk.timestamp = timestamps.get(chunk.page_start)
    log.info("%s: %d pages → %d chunks", source.name, len(pages), len(chunks))

    topics = extract_topics(chunks, on_progress)
    log.info("%s: %d topics found", source.name, len(topics))
    return SourceExtraction(source=source, pages=len(pages), chunks=chunks, topics=topics)


def build_space_graph(space_id: str, extractions: list[SourceExtraction], on_stage: Stage | None = None) -> SpaceGraph:
    """`extractions` in the order the sources were added; that order decides where a topic is first seen."""
    stage = on_stage or (lambda _name: None)
    # Captured before any LLM call, so the versions match the prompts that were actually used.
    extracted_by = ExtractedBy(model=model_label(), prompts={name: prompt_version(name) for name in PROMPTS})

    chunks = [c for e in extractions for c in e.chunks]
    position = {c.key: i for i, c in enumerate(chunks)}
    raw = [
        t.model_copy(update={"first_seen": min(position[k] for k in t.chunks)})
        for e in extractions
        for t in e.topics
        if t.chunks
    ]

    stage("merging topics")
    topics = merge_topics(sorted(raw, key=lambda t: t.first_seen))
    log.info("%d topics → %d after merge", len(raw), len(topics))

    stage("grouping units")
    units = group_units(topics) if topics else []

    stage("mapping prerequisites")
    prereqs = extract_prereqs(topics, units) if topics else []
    log.info("%d units, %d prerequisite edges", len(units), len(prereqs))

    return SpaceGraph(
        space_id=space_id,
        sources=[e.source for e in extractions],
        chunks=chunks,
        topics=topics,
        units=units,
        prereqs=prereqs,
        extracted_by=extracted_by,
    )
