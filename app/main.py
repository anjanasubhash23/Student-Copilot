"""FastAPI application factory.

Run with `uvicorn --factory app.main:create_app`. A factory (rather than a module-level
`app`) means importing this module has no side effects, and tests can pass their own Settings.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI

from app import health
from app.settings import Settings, get_settings
from core.graph.client import create_driver

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        driver = create_driver(settings)
        app.state.neo4j_driver = driver
        log.info("Study Copilot starting (env=%s)", settings.app_env)
        try:
            yield
        finally:
            driver.close()

    app = FastAPI(title="Study Copilot", version=version("study-copilot"), lifespan=lifespan)
    app.state.settings = settings
    app.include_router(health.router)
    return app
