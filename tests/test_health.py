from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import AuthError, ServiceUnavailable

from app import main
from app.settings import Settings


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
    assert r.json() == {"status": "ok", "neo4j": "ok"}


@pytest.mark.parametrize("error", [ServiceUnavailable("connection refused"), AuthError("bad credentials")])
def test_ready_returns_503_when_neo4j_unavailable(client: TestClient, driver: FakeDriver, error: Exception) -> None:
    driver.error = error
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "neo4j": "unavailable"}


def test_driver_closed_on_shutdown(settings: Settings, driver: FakeDriver) -> None:
    with TestClient(main.create_app(settings)):
        assert not driver.closed
    assert driver.closed
