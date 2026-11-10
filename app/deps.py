"""Request dependencies: settings, a SQLite connection per request, the Neo4j driver, the signed-in user,
and the study space being addressed (404 unless the user owns it: spaces are private)."""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from neo4j import Driver

from app.settings import Settings
from core.graph.queries import get_space_map
from core.graph.space_map import SpaceMap
from core.spaces import StudySpace
from core.storage import sqlite
from core.storage.spaces import SqliteStudySpaceRepository
from core.storage.users import SqliteUserRepository, User

SESSION_COOKIE = "sc_session"


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_db(settings: Annotated[Settings, Depends(get_settings_dep)]) -> Iterator[sqlite3.Connection]:
    conn = sqlite.connect(settings.sqlite_path, create=False)
    try:
        yield conn
    finally:
        conn.close()


def get_driver(request: Request) -> Driver:
    driver: Driver = request.app.state.neo4j_driver
    return driver


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
Db = Annotated[sqlite3.Connection, Depends(get_db)]
Neo4j = Annotated[Driver, Depends(get_driver)]


def session_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request, conn: Db) -> User:
    token = session_token(request)
    user = SqliteUserRepository(conn).user_for_token(token) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in first", headers={"WWW-Authenticate": "Bearer"})
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def owned_space(space_id: str, user: CurrentUser, conn: Db) -> StudySpace:
    space = SqliteStudySpaceRepository(conn).get(space_id)
    # Someone else's space answers exactly like a missing one, so ids can't be probed.
    if space is None or space.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "study space not found")
    return space


Space = Annotated[StudySpace, Depends(owned_space)]


def ready_map(space: Space, driver: Neo4j) -> SpaceMap:
    if space.graph_status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "the topic map isn't ready yet; add a source and wait")
    space_map = get_space_map(space.id, driver)
    if not space_map.topics:
        raise HTTPException(status.HTTP_409_CONFLICT, "no topics were found in this space's sources")
    return space_map


Map = Annotated[SpaceMap, Depends(ready_map)]
