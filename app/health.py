"""Liveness (`/health`) and readiness (`/ready`) endpoints.

`/health` never touches dependencies, so a database outage doesn't get the API process restarted.
`/ready` checks Neo4j and SQLite and returns 503 if either is unusable.
The LLM provider isn't checked: it's optional for serving the API, and Ollama may not be running.
"""

import logging
import sqlite3
from contextlib import closing
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError
from pydantic import BaseModel

from app.settings import Settings
from core.storage import sqlite

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

Check = Literal["ok", "unavailable"]


class Health(BaseModel):
    status: Literal["ok"]
    version: str


class Readiness(BaseModel):
    status: Check
    neo4j: Check
    sqlite: Check


def get_neo4j_driver(request: Request) -> Driver:
    driver: Driver = request.app.state.neo4j_driver
    return driver


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _check_neo4j(driver: Driver) -> Check:
    try:
        driver.verify_connectivity()
    except (DriverError, Neo4jError) as exc:
        log.warning("Neo4j readiness check failed: %s: %s", type(exc).__name__, exc)
        return "unavailable"
    return "ok"


def _check_sqlite(settings: Settings) -> Check:
    try:
        # create=False: a deleted database file should fail the check, not be silently recreated empty.
        with closing(sqlite.connect(settings.sqlite_path, create=False)) as conn:
            version = sqlite.schema_version(conn)
    except sqlite3.Error as exc:
        log.warning("SQLite readiness check failed: %s: %s", type(exc).__name__, exc)
        return "unavailable"
    if version != sqlite.SCHEMA_VERSION:
        log.warning("SQLite schema is v%d, expected v%d", version, sqlite.SCHEMA_VERSION)
        return "unavailable"
    return "ok"


@router.get("/health")
def health(request: Request) -> Health:
    return Health(status="ok", version=request.app.version)


@router.get("/ready", responses={503: {"model": Readiness}})
def ready(
    response: Response,
    driver: Annotated[Driver, Depends(get_neo4j_driver)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> Readiness:
    neo4j, sqlite_ = _check_neo4j(driver), _check_sqlite(settings)
    if neo4j == sqlite_ == "ok":
        return Readiness(status="ok", neo4j=neo4j, sqlite=sqlite_)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Readiness(status="unavailable", neo4j=neo4j, sqlite=sqlite_)
