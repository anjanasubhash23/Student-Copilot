from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

GraphStatus = Literal["empty", "building", "ready", "failed"]
ExamStyle = Literal["general"]  # presets (university, competitive, custom) come with V2


class StudySpace(BaseModel):
    id: str
    name: Name
    created_at: datetime
    owner_id: str | None = None  # None: made with the CLI, not visible in the API
    exam_style: ExamStyle = "general"
    graph_status: GraphStatus = "empty"
    graph_error: str | None = None

    @classmethod
    def new(cls, name: str, owner_id: str | None = None) -> "StudySpace":
        """Ids and timestamps are made here, not by the database, so every repository behaves the same."""
        return cls(id=uuid4().hex, name=name, created_at=datetime.now(UTC), owner_id=owner_id)
