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
    # 2: sources and the background job queue
    [
        "ALTER TABLE study_spaces ADD COLUMN graph_status TEXT NOT NULL DEFAULT 'empty'",
        "ALTER TABLE study_spaces ADD COLUMN graph_error TEXT",
        """
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            uri TEXT,
            storage_path TEXT,
            content_hash TEXT,
            pages INTEGER,
            status TEXT NOT NULL,
            stage TEXT,
            progress REAL NOT NULL DEFAULT 0,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX sources_space ON sources(space_id, created_at)",
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            source_id TEXT REFERENCES sources(id) ON DELETE CASCADE,
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'queued',
            stage TEXT,
            progress REAL NOT NULL DEFAULT 0,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            heartbeat_at TEXT,
            finished_at TEXT
        )
        """,
        "CREATE INDEX jobs_queue ON jobs(status, id)",
    ],
    # 3: users and the learning loop
    [
        """
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "ALTER TABLE study_spaces ADD COLUMN owner_id TEXT REFERENCES users(id) ON DELETE CASCADE",
        "ALTER TABLE study_spaces ADD COLUMN exam_style TEXT NOT NULL DEFAULT 'general'",
        "CREATE INDEX study_spaces_owner ON study_spaces(owner_id, created_at)",
        """
        CREATE TABLE questions (
            id TEXT PRIMARY KEY,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            topic_id TEXT NOT NULL,
            type TEXT NOT NULL,
            stem TEXT NOT NULL,
            options TEXT NOT NULL DEFAULT '[]',
            correct TEXT NOT NULL DEFAULT '[]',
            answer TEXT NOT NULL DEFAULT '',
            num_low REAL,
            num_high REAL,
            rubric TEXT NOT NULL DEFAULT '',
            explanation TEXT NOT NULL DEFAULT '',
            solution_code TEXT,
            chunk_id TEXT NOT NULL,
            validation TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL,
            extracted_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX questions_topic ON questions(space_id, topic_id, status)",
        """
        CREATE TABLE attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            topic_id TEXT NOT NULL,
            response TEXT NOT NULL,
            correct INTEGER NOT NULL,
            score REAL NOT NULL,
            mode TEXT NOT NULL,
            ts TEXT NOT NULL
        )
        """,
        "CREATE INDEX attempts_user ON attempts(user_id, space_id, ts)",
        """
        CREATE TABLE mastery (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            topic_id TEXT NOT NULL,
            p_known REAL NOT NULL,
            n_attempts INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, topic_id)
        )
        """,
        "CREATE INDEX mastery_space ON mastery(user_id, space_id)",
        # Every change to p_known, from an answer or from diagnostic propagation; the progress view is built from it.
        """
        CREATE TABLE mastery_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            topic_id TEXT NOT NULL,
            p_known REAL NOT NULL,
            cause TEXT NOT NULL,
            ts TEXT NOT NULL
        )
        """,
        "CREATE INDEX mastery_events_user ON mastery_events(user_id, space_id, ts)",
        """
        CREATE TABLE diagnostics (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            asked TEXT NOT NULL DEFAULT '[]',
            current_question_id TEXT REFERENCES questions(id) ON DELETE SET NULL,
            answered INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ],
    # 4: sign-in sessions and flashcards
    [
        """
        CREATE TABLE sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE flashcards (
            id TEXT PRIMARY KEY,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            topic_id TEXT NOT NULL,
            front TEXT NOT NULL,
            back TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            extracted_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX flashcards_topic ON flashcards(space_id, topic_id)",
        """
        CREATE TABLE reviews (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            flashcard_id TEXT NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
            space_id TEXT NOT NULL REFERENCES study_spaces(id) ON DELETE CASCADE,
            card TEXT NOT NULL,
            due_at TEXT NOT NULL,
            last_review TEXT,
            PRIMARY KEY (user_id, flashcard_id)
        )
        """,
        "CREATE INDEX reviews_due ON reviews(user_id, space_id, due_at)",
    ],
    # 5: LLM usage per job (eval: ingestion time and cost)
    [
        "ALTER TABLE jobs ADD COLUMN llm_calls INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN llm_cached INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN input_tokens INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN output_tokens INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN llm_seconds REAL NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN llm_model TEXT",
    ],
]

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: Path, *, create: bool = True) -> sqlite3.Connection:
    """Open a connection. With create=False a missing database raises instead of being created empty."""
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    # as_uri() percent-encodes spaces etc. in the path
    # check_same_thread=False: FastAPI may open a request's connection in one worker thread and use it in
    # another. Each connection is still used by one request (or the job worker) at a time.
    conn = sqlite3.connect(
        f"{path.resolve().as_uri()}?mode={'rwc' if create else 'rw'}", uri=True, check_same_thread=False
    )
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
