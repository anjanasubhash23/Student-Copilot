"""SQLite connections and schema migrations.

The schema version is stored in SQLite's built-in `PRAGMA user_version`. To change the schema,
append a migration to MIGRATIONS; never edit one that has already shipped.
"""

import sqlite3
from pathlib import Path

# Each migration is a list of statements, applied in one transaction.
MIGRATIONS: list[list[str]] = [
    [
        """
        CREATE TABLE study_spaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ],
]

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: Path, *, create: bool = True) -> sqlite3.Connection:
    """Open a connection. With create=False a missing database raises instead of being created empty."""
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    # as_uri() percent-encodes spaces etc. in the path
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode={'rwc' if create else 'rw'}", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    version: int = conn.execute("PRAGMA user_version").fetchone()[0]
    return version


def migrate(conn: sqlite3.Connection) -> None:
    """Bring the schema up to SCHEMA_VERSION. Refuses to run against a database from newer code."""
    current = schema_version(conn)
    if current > SCHEMA_VERSION:
        raise RuntimeError(f"database schema v{current} is newer than this code (v{SCHEMA_VERSION})")
    # WAL lets readers and a writer work concurrently; it can't be switched on inside a transaction.
    conn.execute("PRAGMA journal_mode = WAL")
    for version, statements in enumerate(MIGRATIONS[current:], start=current + 1):
        conn.execute("BEGIN")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")
        except sqlite3.Error:
            conn.rollback()
            raise
        conn.commit()
