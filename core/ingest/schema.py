from pydantic import BaseModel, Field


class Page(BaseModel):
    number: int
    text: str


class Chunk(BaseModel):
    id: int = Field(description="Position of the chunk within its source, from 0.")
    page_start: int
    page_end: int
    text: str


class Topic(BaseModel):
    name: str
    summary: str
    pages: list[int] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    chunks: list[int] = Field(default_factory=list, description="Ids of the chunks the topic was found in.")

    @property
    def first_seen(self) -> int:
        """Page where the material first introduces the topic (0 if unknown)."""
        return min(self.pages, default=0)


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


class SpaceGraph(BaseModel):
    """The topic graph built from one source, for one study space."""

    space_id: str
    source_id: str = Field(description="Content hash of the source file, so re-ingesting it is recognisable.")
    source: str = Field(description="File name of the source.")
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
