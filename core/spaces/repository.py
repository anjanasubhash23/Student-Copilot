"""The storage contract business logic depends on. SQLite implements it today (core.storage);
a PostgreSQL implementation would only need to pass the same tests in tests/test_spaces_repository.py.
"""

from typing import Protocol

from core.spaces.models import GraphStatus, StudySpace


class AlreadyExistsError(Exception):
    """Raised instead of a backend-specific integrity error, so callers don't depend on the backend."""


class StudySpaceRepository(Protocol):
    def add(self, space: StudySpace) -> None:
        """Raises AlreadyExistsError if a space with this id exists."""
        ...

    def get(self, space_id: str) -> StudySpace | None: ...

    def list_all(self) -> list[StudySpace]:
        """Oldest first."""
        ...

    def list_for_owner(self, owner_id: str) -> list[StudySpace]:
        """Oldest first."""
        ...

    def set_graph_status(self, space_id: str, status: GraphStatus, error: str | None = None) -> None: ...

    def delete(self, space_id: str) -> None:
        """Deletes the space and, by cascade, its sources, jobs, questions, attempts and mastery rows."""
        ...
