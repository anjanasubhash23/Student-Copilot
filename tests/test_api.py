"""End-to-end through the HTTP API, with Neo4j and the LLM replaced by fakes."""

import socket
from collections.abc import Iterator
from contextlib import closing
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import deps, main
from app.routes import learning, spaces
from app.settings import Settings
from core.graph.space_map import SpaceMap, TopicInfo
from core.questions import bank, flashcards
from core.questions.schema import FlashcardsOut, QuestionsOut, ValidationOut
from core.storage import sqlite
from core.storage.jobs import SqliteJobQueue
from core.storage.spaces import SqliteStudySpaceRepository
from core.tutor import explain as explain_mod
from tests.conftest import FakeLLM
from tests.test_health import FakeDriver

CHUNK = {
    "id": "c1",
    "text": "A relation is in 3NF when ...",
    "source": "dbms.pdf",
    "kind": "pdf",
    "page_start": 4,
    "page_end": 4,
    "timestamp": None,
}


@pytest.fixture
def app_client(settings: Settings, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "create_driver", lambda _settings: FakeDriver())
    with TestClient(main.create_app(settings)) as c:
        yield c


def _register(client: TestClient, email: str = "ada@example.com") -> dict[str, Any]:
    r = client.post("/auth/register", json={"email": email, "password": "correct horse"})
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def _space(client: TestClient, name: str = "DBMS") -> str:
    r = client.post("/spaces", json={"name": name})
    assert r.status_code == 201
    return str(r.json()["id"])


def test_register_login_logout(app_client: TestClient) -> None:
    assert app_client.get("/auth/me").status_code == 401
    _register(app_client)
    assert app_client.get("/auth/me").json()["email"] == "ada@example.com"
    assert (
        app_client.post("/auth/register", json={"email": "ADA@example.com", "password": "whatever1"}).status_code == 409
    )
    app_client.post("/auth/logout")
    assert app_client.get("/auth/me").status_code == 401
    assert (
        app_client.post("/auth/login", json={"email": "ada@example.com", "password": "wrong pass"}).status_code == 401
    )
    token = app_client.post("/auth/login", json={"email": "ada@example.com", "password": "correct horse"}).json()[
        "token"
    ]
    app_client.cookies.clear()
    assert app_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_spaces_are_private(app_client: TestClient, settings: Settings) -> None:
    _register(app_client, "ada@example.com")
    space_id = _space(app_client)
    app_client.cookies.clear()
    _register(app_client, "bob@example.com")
    assert app_client.get("/spaces").json() == []
    for method, path in [("get", ""), ("get", "/status"), ("get", "/graph"), ("delete", "")]:
        assert getattr(app_client, method)(f"/spaces/{space_id}{path}").status_code == 404


def test_upload_queues_ingestion_and_reports_status(app_client: TestClient, settings: Settings) -> None:
    _register(app_client)
    space_id = _space(app_client)
    files = {"file": ("notes.md", b"# Keys\nA key identifies a row.", "application/octet-stream")}
    r = app_client.post(f"/spaces/{space_id}/sources", files=files)
    assert r.status_code == 202, r.text
    assert r.json()["kind"] == "text"
    assert r.json()["storage_path"] is None
    # the same file again is refused
    assert app_client.post(f"/spaces/{space_id}/sources", files=files).status_code == 409
    bad = {"file": ("evil.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")}
    assert app_client.post(f"/spaces/{space_id}/sources", files=bad).status_code == 415

    status = app_client.get(f"/spaces/{space_id}/status").json()
    assert status["graph"]["status"] == "empty"
    [source] = status["sources"]
    assert (source["status"], source["storage_path"]) == ("queued", None)
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        job = SqliteJobQueue(conn).claim()
    assert job is not None and (job.kind, job.source_id) == ("ingest_source", source["id"])

    assert app_client.post(f"/spaces/{space_id}/sources/{source['id']}/retry").status_code == 409  # not failed
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        conn.execute("UPDATE sources SET status = 'failed', error = 'llm down'")
        conn.commit()
    retried = app_client.post(f"/spaces/{space_id}/sources/{source['id']}/retry").json()
    assert (retried["status"], retried["error"]) == ("queued", None)


def test_links_are_checked_for_ssrf(app_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port, **kw: [(socket.AF_INET, 1, 6, "", ("10.0.0.1", port))]
    )
    _register(app_client)
    space_id = _space(app_client)
    r = app_client.post(f"/spaces/{space_id}/sources/link", json={"url": "http://intranet.local/"})
    assert r.status_code == 422
    assert "private or internal" in r.json()["detail"]
    yt = app_client.post(f"/spaces/{space_id}/sources/link", json={"url": "https://youtu.be/dQw4w9WgXcQ"})
    assert yt.status_code == 202 and yt.json()["kind"] == "youtube"


def test_learning_needs_a_map(app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _register(app_client)
    space_id = _space(app_client)
    r = app_client.post(f"/spaces/{space_id}/practice/next", json={})
    assert r.status_code == 409 and "add a source" in r.json()["detail"]

    # first build still running: nothing to learn from yet
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        SqliteStudySpaceRepository(conn).set_graph_status(space_id, "building")
    monkeypatch.setattr(deps, "get_space_map", lambda sid, driver: SpaceMap.build([], []))
    r = app_client.post(f"/spaces/{space_id}/practice/next", json={})
    assert r.status_code == 409 and "still being built" in r.json()["detail"]

    # a rebuild (another source added) keeps the previous map usable
    monkeypatch.setattr(deps, "get_space_map", lambda sid, driver: SpaceMap.build([TopicInfo(id="t", name="T")], []))
    monkeypatch.setattr(bank, "topic_chunks", lambda *a, **kw: [])
    r = app_client.post(f"/spaces/{space_id}/practice/next", json={})
    assert r.status_code == 200


# The learning loop on a two-topic map: Relational Model → 3NF


def _ready_space(
    app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch, fake: FakeLLM
) -> tuple[str, SpaceMap]:
    _register(app_client)
    space_id = _space(app_client)
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        SqliteStudySpaceRepository(conn).set_graph_status(space_id, "ready")
    space_map = SpaceMap.build(
        [
            TopicInfo(id="rel", name="Relational Model", first_seen=0),
            TopicInfo(id="3nf", name="Third Normal Form", first_seen=1),
        ],
        [("rel", "3nf", 1.0)],
    )
    monkeypatch.setattr(deps, "get_space_map", lambda sid, driver: space_map)
    monkeypatch.setattr(spaces, "get_space_map", lambda sid, driver: space_map)
    monkeypatch.setattr(bank, "topic_chunks", lambda *a, **kw: [CHUNK])
    monkeypatch.setattr(learning, "get_chunks", lambda *a, **kw: [CHUNK])

    def questions(prompt: str) -> QuestionsOut:
        return QuestionsOut.model_validate(
            {
                "questions": [
                    {
                        "type": "mcq",
                        "stem": f"Q{i}?",
                        "options": ["a", "b", "c", "d"],
                        "correct": [i % 4],
                        "answer": "",
                        "explanation": "because",
                        "source": 1,
                    }
                    for i in range(2)
                ]
            }
        )

    fake.replies[QuestionsOut] = questions
    fake.replies[ValidationOut] = lambda prompt: ValidationOut(valid=True, reason="ok")
    return space_id, space_map


def test_practice_updates_mastery_and_queues_flashcards(
    app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLM
) -> None:
    space_id, _ = _ready_space(app_client, settings, monkeypatch, fake_llm)
    nxt = app_client.post(f"/spaces/{space_id}/practice/next", json={}).json()
    assert nxt["topic"] == "Relational Model"  # 3NF's prerequisite isn't ready yet
    question = nxt["question"]
    assert "correct" not in question and "answer" not in question

    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        right = conn.execute("SELECT correct FROM questions WHERE id = ?", (question["id"],)).fetchone()[0]
    choice = int(right.strip("[]"))
    r = app_client.post(
        f"/spaces/{space_id}/practice/answer", json={"question_id": question["id"], "response": {"choice": choice}}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mark"]["correct"] is True
    assert body["mastery"]["p_known"] > 0.2
    assert body["source"] == {"name": "dbms.pdf", "location": "p. 4"}

    graph_topics = {t["id"]: t for t in app_client.get(f"/spaces/{space_id}/graph").json()["topics"]}
    assert graph_topics["rel"]["p_known"] == pytest.approx(body["mastery"]["p_known"], abs=1e-4)
    assert graph_topics["3nf"]["assessed"] is False

    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        job = SqliteJobQueue(conn).claim()
    assert job is not None and (job.kind, job.payload) == ("flashcards", {"topic_id": "rel"})

    bad = app_client.post(f"/spaces/{space_id}/practice/answer", json={"question_id": question["id"], "response": {}})
    assert bad.status_code == 422


def test_diagnostic_runs_to_completion_with_propagation(
    app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLM
) -> None:
    space_id, _ = _ready_space(app_client, settings, monkeypatch, fake_llm)
    step = app_client.post(f"/spaces/{space_id}/diagnostic").json()
    assert (step["number"], step["total"], step["done"]) == (1, 2, False)
    answered = []
    while not step["done"]:
        q = step["question"]
        with closing(sqlite.connect(settings.sqlite_path)) as conn:
            right = int(
                conn.execute("SELECT correct FROM questions WHERE id = ?", (q["id"],)).fetchone()[0].strip("[]")
            )
        r = app_client.post(
            f"/spaces/{space_id}/diagnostic/{step['diagnostic_id']}/answer",
            json={"question_id": q["id"], "response": {"choice": right}},
        )
        assert r.status_code == 200, r.text
        answered.append(r.json()["result"])
        step = r.json()["next"]
    assert len(answered) == 2
    # answering 3NF right also raised its prerequisite, Relational Model
    first = answered[0]
    if first["mastery"]["topic_id"] == "3nf":
        assert [t["topic_id"] for t in first["also_updated"]] == ["rel"]
    # replaying an answer is refused
    again = app_client.post(
        f"/spaces/{space_id}/diagnostic/{step['diagnostic_id']}/answer",
        json={"question_id": q["id"], "response": {"choice": 0}},
    )
    assert again.status_code == 409
    progress = app_client.get(f"/spaces/{space_id}/progress").json()
    assert (progress["topics"], progress["assessed"]) == (2, 2)


def test_explain_cites_sources_and_covers_weak_prerequisites(
    app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLM
) -> None:
    space_id, _ = _ready_space(app_client, settings, monkeypatch, fake_llm)
    monkeypatch.setattr(explain_mod, "search_topics", lambda *a, **kw: [{"id": "3nf", "name": "Third Normal Form"}])
    monkeypatch.setattr(explain_mod, "search_chunks", lambda *a, **kw: [{**CHUNK, "id": "c2", "topics": ["3nf"]}])
    monkeypatch.setattr(explain_mod, "topic_chunks", lambda sid, tid, **kw: [{**CHUNK, "id": f"chunk-{tid}"}])
    fake_llm.replies[str] = lambda prompt: "First, relations [1]. Then 3NF [2]."
    r = app_client.post(f"/spaces/{space_id}/explain", json={"question": "What is 3NF?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["topic"] == "Third Normal Form"
    assert body["covered_prerequisites"] == ["Relational Model"]
    assert [c["chunk_id"] for c in body["citations"]] == ["chunk-rel", "c2", "chunk-3nf"]
    assert body["citations"][0]["location"] == "p. 4"
    prompt = fake_llm.prompts[-1]
    assert "hasn't mastered these prerequisites yet: Relational Model" in prompt


def test_flashcards_generate_and_review(
    app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLM
) -> None:
    space_id, space_map = _ready_space(app_client, settings, monkeypatch, fake_llm)
    fake_llm.replies[FlashcardsOut] = lambda prompt: FlashcardsOut.model_validate(
        {
            "cards": [
                {"front": "3NF?", "back": "No transitive deps.", "source": 1},
                {"front": "bad", "back": "x", "source": 7},
            ]
        }
    )
    monkeypatch.setattr(flashcards, "get_space_map", lambda sid, driver: space_map)
    monkeypatch.setattr(flashcards, "topic_chunks", lambda *a, **kw: [CHUNK])
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        driver: Any = FakeDriver()
        assert flashcards.ensure_flashcards(conn, driver, space_id, "3nf") == 1  # the uncited card is dropped
        assert flashcards.ensure_flashcards(conn, driver, space_id, "3nf") == 0
    [card] = app_client.get(f"/spaces/{space_id}/flashcards/due").json()["cards"]
    assert (card["front"], card["topic"], card["new"]) == ("3NF?", "Third Normal Form", True)
    r = app_client.post(f"/flashcards/{card['id']}/review", json={"rating": "good"})
    assert r.status_code == 200
    assert app_client.get(f"/spaces/{space_id}/flashcards/due").json()["cards"] == []
    app_client.cookies.clear()
    _register(app_client, "eve@example.com")
    assert app_client.post(f"/flashcards/{card['id']}/review", json={"rating": "easy"}).status_code == 404


def test_delete_space_removes_everything(
    app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    deleted: list[str] = []
    monkeypatch.setattr(spaces, "delete_space_graph", lambda sid, driver: deleted.append(sid))
    _register(app_client)
    space_id = _space(app_client)
    app_client.post(f"/spaces/{space_id}/sources", files={"file": ("n.md", b"# A\nb", "text/markdown")})
    assert (settings.data_dir / "uploads" / space_id).exists()
    assert app_client.delete(f"/spaces/{space_id}").status_code == 204
    assert deleted == [space_id]
    assert not (settings.data_dir / "uploads" / space_id).exists()
    assert app_client.get(f"/spaces/{space_id}").status_code == 404


def test_sign_in_is_rate_limited(app_client: TestClient, settings: Settings) -> None:
    _register(app_client)
    for _ in range(settings.login_attempts_per_15_min - 1):  # register counted as one attempt
        assert (
            app_client.post("/auth/login", json={"email": "ada@example.com", "password": "wrong pass"}).status_code
            == 401
        )
    r = app_client.post("/auth/login", json={"email": "ada@example.com", "password": "correct horse"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_registration_can_be_closed(settings: Settings, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "create_driver", lambda _settings: FakeDriver())
    closed = settings.model_copy(update={"allow_registration": False})
    with TestClient(main.create_app(closed)) as client:
        r = client.post("/auth/register", json={"email": "x@example.com", "password": "password1"})
    assert r.status_code == 403


def test_space_limit(app_client: TestClient, settings: Settings) -> None:
    _register(app_client)
    app_client.app.state.settings = settings.model_copy(update={"max_spaces_per_user": 2})  # type: ignore[attr-defined]
    _space(app_client, "a")
    _space(app_client, "b")
    assert app_client.post("/spaces", json={"name": "c"}).status_code == 409


def test_llm_requests_are_rate_limited(
    app_client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch, fake_llm: FakeLLM
) -> None:
    space_id, _ = _ready_space(app_client, settings, monkeypatch, fake_llm)
    app_client.app.state.settings = settings.model_copy(update={"llm_requests_per_minute": 2})  # type: ignore[attr-defined]
    codes = [app_client.post(f"/spaces/{space_id}/practice/next", json={}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_secure_cookies_default_on_in_production(settings: Settings) -> None:
    assert not settings.secure_cookies
    assert settings.model_copy(update={"app_env": "production"}).secure_cookies
    assert not settings.model_copy(update={"app_env": "production", "session_cookie_secure": False}).secure_cookies
