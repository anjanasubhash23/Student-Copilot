from collections.abc import Iterator
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import AuthError, ServiceUnavailable

from app import main
from app.settings import Settings
from core.storage import sqlite


class FakeDriver:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.closed = False

    def verify_connectivity(self) -> None:
        if self.error:
            raise self.error

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> FakeDriver:
    fake = FakeDriver()
    monkeypatch.setattr(main, "create_driver", lambda _settings: fake)
    return fake


@pytest.fixture
def client(settings: Settings, driver: FakeDriver) -> Iterator[TestClient]:
    with TestClient(main.create_app(settings)) as c:
        yield c


def test_health_reports_ok_and_version(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_health_does_not_touch_neo4j(client: TestClient, driver: FakeDriver) -> None:
    driver.error = ServiceUnavailable("down")
    assert client.get("/health").status_code == 200


def test_ready_when_neo4j_reachable(client: TestClient) -> None:
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "neo4j": "ok", "sqlite": "ok"}


@pytest.mark.parametrize("error", [ServiceUnavailable("connection refused"), AuthError("bad credentials")])
def test_ready_returns_503_when_neo4j_unavailable(client: TestClient, driver: FakeDriver, error: Exception) -> None:
    driver.error = error
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "neo4j": "unavailable", "sqlite": "ok"}


def test_startup_creates_and_migrates_sqlite(client: TestClient, settings: Settings) -> None:
    with closing(sqlite.connect(settings.sqlite_path, create=False)) as conn:
        assert sqlite.schema_version(conn) == sqlite.SCHEMA_VERSION


def test_ready_returns_503_when_sqlite_missing(client: TestClient, settings: Settings) -> None:
    settings.sqlite_path.unlink()
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "neo4j": "ok", "sqlite": "unavailable"}
    assert not settings.sqlite_path.exists()  # the check must not recreate an empty database


def test_ready_returns_503_when_sqlite_schema_outdated(client: TestClient, settings: Settings) -> None:
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        conn.execute("PRAGMA user_version = 0")
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["sqlite"] == "unavailable"


def test_driver_closed_on_shutdown(settings: Settings, driver: FakeDriver) -> None:
    with TestClient(main.create_app(settings)):
        assert not driver.closed
    assert driver.closed
