"""Liveness (`/health`) and readiness (`/ready`) endpoints.

`/health` never touches dependencies, so a Neo4j outage doesn't get the API process restarted.
`/ready` checks Neo4j and returns 503 when it can't be reached.
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str


class Readiness(BaseModel):
    status: Literal["ok", "unavailable"]
    neo4j: Literal["ok", "unavailable"]


def get_neo4j_driver(request: Request) -> Driver:
    driver: Driver = request.app.state.neo4j_driver
    return driver


@router.get("/health")
def health(request: Request) -> Health:
    return Health(status="ok", version=request.app.version)


@router.get("/ready", responses={503: {"model": Readiness}})
def ready(response: Response, driver: Annotated[Driver, Depends(get_neo4j_driver)]) -> Readiness:
    try:
        driver.verify_connectivity()
    except (DriverError, Neo4jError) as exc:
        log.warning("Neo4j readiness check failed: %s: %s", type(exc).__name__, exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Readiness(status="unavailable", neo4j="unavailable")
    return Readiness(status="ok", neo4j="ok")
