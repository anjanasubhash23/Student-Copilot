"""FastAPI application factory.

Run with `uvicorn --factory app.main:create_app`. A factory (rather than a module-level
`app`) means importing this module has no side effects, and tests can pass their own Settings.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing
from importlib.metadata import version

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from neo4j.exceptions import DriverError, Neo4jError

from app import health
from app.routes import auth, flashcards, learning, spaces
from app.settings import Settings, get_settings
from core.graph.client import create_driver
from core.storage import sqlite

log = logging.getLogger(__name__)

WORKER_STOP_TIMEOUT = 10.0


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Fail startup, rather than the first request, if the database can't be opened or migrated.
        with closing(sqlite.connect(settings.sqlite_path)) as conn:
            sqlite.migrate(conn)
        driver = create_driver(settings)
        app.state.neo4j_driver = driver
        worker = None
        if settings.run_worker:
            from workers.run import start_in_thread

            worker = start_in_thread(settings, driver)
        log.info(
            "Study Copilot starting (env=%s, llm=%s/%s, worker=%s)",
            settings.app_env,
            settings.llm_provider,
            settings.llm_model,
            "in-process" if worker else "external",
        )
        try:
            yield
        finally:
            if worker:
                thread, stop = worker
                stop.set()
                thread.join(WORKER_STOP_TIMEOUT)  # a job mid-LLM-call is abandoned; it's requeued on restart
            driver.close()

    app = FastAPI(title="Study Copilot", version=version("study-copilot"), lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(spaces.router)
    app.include_router(learning.router)
    app.include_router(flashcards.router)

    @app.exception_handler(DriverError)
    @app.exception_handler(Neo4jError)
    async def graph_unavailable(_request: Request, exc: Exception) -> JSONResponse:
        log.warning("Neo4j error: %s: %s", type(exc).__name__, exc)
        return JSONResponse(
            {"detail": "the topic graph database isn't reachable; is Neo4j running?"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    @app.exception_handler(httpx.TransportError)
    @app.exception_handler(ConnectionError)
    async def llm_unavailable(_request: Request, exc: Exception) -> JSONResponse:
        log.warning("LLM connection error: %s: %s", type(exc).__name__, exc)
        return JSONResponse(
            {"detail": f"the language model ({settings.llm_provider}) isn't reachable; is it running?"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return app
