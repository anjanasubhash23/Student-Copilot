"""Contract tests for StudySpaceRepository. A new implementation (e.g. PostgreSQL) is
added to the `repo` fixture's params and must pass the same tests."""

from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.spaces import AlreadyExistsError, StudySpace, StudySpaceRepository
from core.storage import sqlite
from core.storage.spaces import SqliteStudySpaceRepository


@pytest.fixture(params=["sqlite"])
def repo(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[StudySpaceRepository]:
    with closing(sqlite.connect(tmp_path / "app.db")) as conn:
        sqlite.migrate(conn)
        yield SqliteStudySpaceRepository(conn)


def test_add_then_get_round_trips(repo: StudySpaceRepository) -> None:
    space = StudySpace.new("  Databases  ")
    repo.add(space)
    assert repo.get(space.id) == space
    assert space.name == "Databases"
    assert space.created_at.tzinfo is not None


def test_get_unknown_returns_none(repo: StudySpaceRepository) -> None:
    assert repo.get("missing") is None


def test_list_all_is_oldest_first(repo: StudySpaceRepository) -> None:
    now = datetime.now(UTC)
    newer = StudySpace(id="b", name="Newer", created_at=now)
    older = StudySpace(id="a", name="Older", created_at=now - timedelta(days=1))
    repo.add(newer)
    repo.add(older)
    assert [s.name for s in repo.list_all()] == ["Older", "Newer"]


def test_duplicate_id_is_rejected(repo: StudySpaceRepository) -> None:
    space = StudySpace.new("Databases")
    repo.add(space)
    with pytest.raises(AlreadyExistsError):
        repo.add(space)
    assert len(repo.list_all()) == 1


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_rejects_invalid_names(name: str) -> None:
    with pytest.raises(ValidationError):
        StudySpace.new(name)
