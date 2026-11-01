from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StudySpace(BaseModel):
    id: str
    name: Name
    created_at: datetime

    @classmethod
    def new(cls, name: str) -> "StudySpace":
        """Ids and timestamps are made here, not by the database, so every repository behaves the same."""
        return cls(id=uuid4().hex, name=name, created_at=datetime.now(UTC))
