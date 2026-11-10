from typing import Literal

from pydantic import BaseModel, Field

SourceKind = Literal["pdf", "pptx", "docx", "text", "web", "youtube"]


class Page(BaseModel):
    """A located piece of a source: a PDF page, a slide, a document section, or a stretch of a video."""

    number: int
    text: str
    timestamp: float | None = Field(default=None, description="Seconds into the video, for YouTube sources.")


class Chunk(BaseModel):
    id: int = Field(description="Position of the chunk within its source, from 0.")
    source_id: str = ""
    page_start: int
    page_end: int
    timestamp: float | None = None
    text: str

    @property
    def key(self) -> str:
        """Unique within a space: `{source_id}:{id}`."""
        return f"{self.source_id}:{self.id}"


class Topic(BaseModel):
    name: str
    summary: str
    aliases: list[str] = Field(default_factory=list)
    chunks: list[str] = Field(default_factory=list, description="Keys of the chunks the topic was found in.")
    first_seen: int = Field(default=0, description="Position of the first chunk that teaches it, across sources.")


class Unit(BaseModel):
    name: str
    order: int
    topics: list[str]


class Prereq(BaseModel):
    topic: str = Field(description="The topic that has the prerequisite.")
    requires: str = Field(description="The topic that must be learned first.")
    reason: str = Field(default="", description="One short clause on why.")
    # Not range-constrained here: a small model answering 1.2 shouldn't fail the whole call. Clamped in prereqs.py.
    confidence: float = Field(default=1.0, description="From 0 to 1: how sure you are that this dependency is real.")


class ExtractedBy(BaseModel):
    """Which model and prompt versions produced the graph, so edges can be traced and re-generated."""

    model: str = Field(description="provider/model, e.g. 'ollama/llama3.1:8b'.")
    prompts: dict[str, str] = Field(description="Prompt name → version (hash of the prompt file).")

    def label(self, prompt: str) -> str:
        return f"{self.model} {prompt}@{self.prompts[prompt]}"


class SourceRef(BaseModel):
    id: str
    name: str
    kind: SourceKind


class SourceExtraction(BaseModel):
    """What ingest keeps per source: its chunks and the topics found in each, before merging across sources."""

    source: SourceRef
    pages: int
    chunks: list[Chunk]
    topics: list[Topic]


class SpaceGraph(BaseModel):
    """The topic graph built from all of a study space's sources."""

    space_id: str
    sources: list[SourceRef]
    chunks: list[Chunk]
    topics: list[Topic]
    units: list[Unit]
    prereqs: list[Prereq]
    extracted_by: ExtractedBy


# LLM output shapes


class TopicDraft(BaseModel):
    name: str = Field(description="Short canonical name, e.g. 'Third Normal Form'.")
    summary: str = Field(description="One sentence.")


class TopicsOut(BaseModel):
    topics: list[TopicDraft]


class UnitDraft(BaseModel):
    name: str
    topics: list[str] = Field(description="Topic names exactly as given, in teaching order.")


class UnitsOut(BaseModel):
    units: list[UnitDraft]


class PrereqsOut(BaseModel):
    edges: list[Prereq]
