from functools import lru_cache

from neo4j import Driver, GraphDatabase

from app.settings import Settings, get_settings


def create_driver(settings: Settings) -> Driver:
    """Build a driver; it connects lazily, so this doesn't fail if Neo4j is down."""
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )


@lru_cache
def get_driver() -> Driver:
    """Process-wide driver for scripts. The API owns its own driver (see app.main)."""
    return create_driver(get_settings())
