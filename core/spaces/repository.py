"""The storage contract business logic depends on. SQLite implements it today (core.storage);
a PostgreSQL implementation would only need to pass the same tests in tests/test_spaces_repository.py.
"""

from typing import Protocol

from core.spaces.models import StudySpace


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
