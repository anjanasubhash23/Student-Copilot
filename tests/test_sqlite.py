import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from core.storage import sqlite


def test_migrate_creates_schema_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "app.db"
    with closing(sqlite.connect(path)) as conn:
        sqlite.migrate(conn)
        sqlite.migrate(conn)
        assert sqlite.schema_version(conn) == sqlite.SCHEMA_VERSION
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "study_spaces" in tables
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_handles_paths_with_spaces(tmp_path: Path) -> None:
    path = tmp_path / "Student Copilot" / "app.db"
    with closing(sqlite.connect(path)) as conn:
        sqlite.migrate(conn)
    assert path.exists()


def test_refuses_database_from_newer_code(tmp_path: Path) -> None:
    with closing(sqlite.connect(tmp_path / "app.db")) as conn:
        conn.execute(f"PRAGMA user_version = {sqlite.SCHEMA_VERSION + 1}")
        with pytest.raises(RuntimeError, match="newer than this code"):
            sqlite.migrate(conn)


def test_failed_migration_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqlite, "MIGRATIONS", [["CREATE TABLE ok (id INTEGER)", "NOT VALID SQL"]])
    monkeypatch.setattr(sqlite, "SCHEMA_VERSION", 1)
    with closing(sqlite.connect(tmp_path / "app.db")) as conn:
        with pytest.raises(sqlite3.OperationalError):
            sqlite.migrate(conn)
        assert sqlite.schema_version(conn) == 0
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = 'ok'").fetchone() is None


def test_connect_without_create_does_not_make_a_file(tmp_path: Path) -> None:
    with pytest.raises(sqlite3.OperationalError):
        sqlite.connect(tmp_path / "missing.db", create=False)
    assert not (tmp_path / "missing.db").exists()
