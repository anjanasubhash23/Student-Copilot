from pydantic import BaseModel, Field


class Page(BaseModel):
    number: int
    text: str


class Chunk(BaseModel):
    id: int
    page_start: int
    page_end: int
    text: str


class Topic(BaseModel):
    name: str
    summary: str
    pages: list[int] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class Unit(BaseModel):
    name: str
    order: int
    topics: list[str]


class Prereq(BaseModel):
    topic: str = Field(description="The topic that has the prerequisite.")
    requires: str = Field(description="The topic that must be learned first.")
    reason: str = Field(default="", description="One short clause on why.")


class CourseGraph(BaseModel):
    course: str
    source: str
    topics: list[Topic]
    units: list[Unit]
    prereqs: list[Prereq]


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
