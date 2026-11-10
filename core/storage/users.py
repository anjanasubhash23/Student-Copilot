"""Users and their sign-in sessions. Only a hash of each session token is stored."""

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel

from core.auth.passwords import hash_password, verify_password
from core.spaces.repository import AlreadyExistsError
from core.storage.clock import iso, now


class User(BaseModel):
    id: str
    email: str
    created_at: datetime


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Verified against when the email is unknown, so a login takes as long whether or not the account exists.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


class SqliteUserRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, email: str, password: str) -> User:
        user = User(id=uuid4().hex, email=email.strip().lower(), created_at=now())
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    (user.id, user.email, hash_password(password), iso(user.created_at)),
                )
        except sqlite3.IntegrityError as exc:
            raise AlreadyExistsError("an account with this email already exists") from exc
        return user

    def get(self, user_id: str) -> User | None:
        row = self._conn.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return _to_user(row) if row else None

    def get_by_email(self, email: str) -> User | None:
        row = self._conn.execute(
            "SELECT id, email, created_at FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return _to_user(row) if row else None

    def authenticate(self, email: str, password: str) -> User | None:
        row = self._conn.execute(
            "SELECT id, email, created_at, password_hash FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        if row is None:
            verify_password(password, _DUMMY_HASH)
            return None
        return _to_user(row) if verify_password(password, row["password_hash"]) else None

    def start_session(self, user_id: str, lifetime: timedelta) -> str:
        """Returns the token to give the client; only its hash is kept."""
        token = secrets.token_urlsafe(32)
        at = now()
        with self._conn:
            self._conn.execute(
                "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (_token_hash(token), user_id, iso(at), iso(at + lifetime)),
            )
        return token

    def user_for_token(self, token: str) -> User | None:
        row = self._conn.execute(
            """
            SELECT u.id, u.email, u.created_at FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (_token_hash(token), iso(now())),
        ).fetchone()
        return _to_user(row) if row else None

    def end_session(self, token: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def _to_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], email=row["email"], created_at=datetime.fromisoformat(row["created_at"]))
