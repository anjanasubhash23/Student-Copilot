"""Study spaces, their sources, ingestion status and topic map."""

import hashlib
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.deps import CurrentUser, Db, Neo4j, SettingsDep, Space
from core.graph.queries import get_space_map
from core.graph.writer import delete_space_graph
from core.mastery.bkt import PRIOR, is_mastered
from core.sources import EXTENSIONS, FetchError, UnsupportedFileError, detect_kind, is_youtube, is_youtube_playlist
from core.sources.fetch import check_url
from core.spaces import StudySpace
from core.spaces.models import ExamStyle, Name
from core.storage.clock import now
from core.storage.files import FileStore
from core.storage.flashcards import SqliteFlashcardRepository
from core.storage.jobs import SqliteJobQueue
from core.storage.learning import SqliteMasteryRepository
from core.storage.sources import Source, SqliteSourceRepository
from core.storage.spaces import SqliteStudySpaceRepository

router = APIRouter(prefix="/spaces", tags=["spaces"])


class NewSpace(BaseModel):
    name: Name
    exam_style: ExamStyle = "general"


@router.post("", status_code=status.HTTP_201_CREATED)
def create_space(body: NewSpace, user: CurrentUser, conn: Db, settings: SettingsDep) -> StudySpace:
    repo = SqliteStudySpaceRepository(conn)
    if len(repo.list_for_owner(user.id)) >= settings.max_spaces_per_user:
        raise HTTPException(status.HTTP_409_CONFLICT, f"you can have at most {settings.max_spaces_per_user} spaces")
    space = StudySpace.new(body.name, owner_id=user.id).model_copy(update={"exam_style": body.exam_style})
    repo.add(space)
    return space


@router.get("")
def list_spaces(user: CurrentUser, conn: Db) -> list[StudySpace]:
    return SqliteStudySpaceRepository(conn).list_for_owner(user.id)


@router.get("/{space_id}")
def get_space(space: Space) -> StudySpace:
    return space


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space(space: Space, conn: Db, driver: Neo4j, settings: SettingsDep) -> None:
    """Deletes the graph first: if Neo4j is down this fails before anything is gone, and can be retried."""
    delete_space_graph(space.id, driver)
    SqliteStudySpaceRepository(conn).delete(space.id)  # cascades to sources, jobs, questions, attempts, mastery
    FileStore(settings.data_dir).delete_space(space.id)


# Sources


def _check_room(conn: Db, space: StudySpace, settings: SettingsDep) -> None:
    active = [s for s in SqliteSourceRepository(conn).list_for_space(space.id) if s.status != "failed"]
    if len(active) >= settings.max_sources_per_space:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a space can have at most {settings.max_sources_per_space} sources"
        )


def _queue(conn: Db, source: Source) -> Source:
    SqliteSourceRepository(conn).add(source)
    SqliteJobQueue(conn).enqueue("ingest_source", source.space_id, source.id)
    return source.model_copy(update={"storage_path": None})  # never expose where uploads are stored


@router.post("/{space_id}/sources", status_code=status.HTTP_202_ACCEPTED)
def upload_source(
    space: Space,
    conn: Db,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="PDF, PPTX, DOCX, MD or TXT")],
) -> Source:
    """Add a file. It's stored, then ingested in the background; follow it with GET /spaces/{id}/status."""
    _check_room(conn, space, settings)
    limit = settings.max_upload_mb * 1_000_000
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"files are limited to {settings.max_upload_mb} MB")
    name = (file.filename or "upload").rsplit("/", 1)[-1][:200]
    try:
        kind = detect_kind(data, name)
    except UnsupportedFileError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    digest = hashlib.sha256(data).hexdigest()
    if existing := SqliteSourceRepository(conn).find_by_hash(space.id, digest):
        raise HTTPException(status.HTTP_409_CONFLICT, f"this file is already in the space as '{existing.name}'")
    source = Source.new(space.id, kind, name, content_hash=digest)
    path = FileStore(settings.data_dir).save_upload(space.id, source.id, EXTENSIONS[kind], data)
    return _queue(conn, source.model_copy(update={"storage_path": str(path)}))


class NewLink(BaseModel):
    url: str = Field(max_length=2000)


@router.post("/{space_id}/sources/link", status_code=status.HTTP_202_ACCEPTED)
def add_link(body: NewLink, space: Space, conn: Db, settings: SettingsDep) -> Source:
    """Add a web page or a YouTube video (its transcript)."""
    _check_room(conn, space, settings)
    url = body.url.strip()
    if is_youtube_playlist(url):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "playlists aren't supported yet; add the videos one at a time"
        )
    if is_youtube(url):
        kind: Literal["web", "youtube"] = "youtube"
    else:
        kind = "web"
        try:
            check_url(url)  # fail fast on a bad link; the worker checks again on every redirect
        except FetchError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _queue(conn, Source.new(space.id, kind, url[:200], uri=url))


@router.delete("/{space_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: str, space: Space, conn: Db, settings: SettingsDep) -> None:
    sources = SqliteSourceRepository(conn)
    source = sources.get(source_id)
    if source is None or source.space_id != space.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    sources.delete(source.id)
    FileStore(settings.data_dir).delete_source(space.id, source.id, source.storage_path)
    if source.status == "ready":
        SqliteJobQueue(conn).enqueue("build_graph", space.id, dedupe=True)


@router.post("/{space_id}/sources/{source_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_source(source_id: str, space: Space, conn: Db) -> Source:
    """Queue a failed source again (e.g. after starting the LLM)."""
    sources = SqliteSourceRepository(conn)
    source = sources.get(source_id)
    if source is None or source.space_id != space.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")
    if source.status != "failed":
        raise HTTPException(status.HTTP_409_CONFLICT, "only a failed source can be retried")
    sources.update(source.id, status="queued", stage=None, progress=0.0, error=None)
    SqliteJobQueue(conn).enqueue("ingest_source", space.id, source.id, dedupe=True)
    return (sources.get(source.id) or source).model_copy(update={"storage_path": None})


class GraphStatus(BaseModel):
    status: str  # empty | building | ready | failed
    stage: str | None = None
    error: str | None = None


class SpaceStatus(BaseModel):
    graph: GraphStatus
    sources: list[Source]


@router.get("/{space_id}/status")
def space_status(space: Space, conn: Db) -> SpaceStatus:
    """Ingestion progress: each source's stage (reading → finding topics → ready) and the map's
    (merging topics → grouping units → mapping prerequisites → writing graph → ready)."""
    jobs = SqliteJobQueue(conn).active_for_space(space.id)
    build = next((j for j in jobs if j.kind == "build_graph"), None)
    graph = GraphStatus(status=space.graph_status, error=space.graph_error)
    if build is not None:
        graph = GraphStatus(status="building", stage=build.stage or "waiting")
    sources = SqliteSourceRepository(conn).list_for_space(space.id)
    for s in sources:  # never expose where uploads are stored
        s.storage_path = None
    return SpaceStatus(graph=graph, sources=sources)


@router.get("/{space_id}/graph")
def space_graph(space: Space, user: CurrentUser, conn: Db, driver: Neo4j) -> dict[str, Any]:
    """Units, topics coloured by the user's mastery, and prerequisite edges: the mastery map."""
    space_map = get_space_map(space.id, driver)
    mastery = SqliteMasteryRepository(conn).for_space(user.id, space.id)
    attempts = SqliteMasteryRepository(conn).attempts_per_topic(user.id, space.id)
    due = SqliteFlashcardRepository(conn).due_counts(user.id, space.id, now())
    units: dict[str, dict[str, Any]] = {}
    for t in space_map.topics.values():
        if t.unit_id and t.unit_id not in units:
            units[t.unit_id] = {"id": t.unit_id, "name": t.unit, "order": t.unit_order}
    return {
        "units": sorted(units.values(), key=lambda u: u["order"]),
        "topics": [
            {
                "id": t.id,
                "name": t.name,
                "summary": t.summary,
                "unit_id": t.unit_id,
                "position": t.position,
                "p_known": round(mastery.get(t.id, PRIOR), 4),
                "assessed": t.id in mastery,
                "mastered": is_mastered(mastery.get(t.id, PRIOR)),
                "attempts": attempts.get(t.id, 0),
                "due_cards": due.get(t.id, 0),
                "prerequisites": sorted(space_map.prereqs.get(t.id, ())),
            }
            for t in sorted(space_map.topics.values(), key=lambda t: (t.unit_order, t.position, t.first_seen))
        ],
        "edges": [
            {"source": pre, "target": dep, "confidence": conf} for (pre, dep), conf in space_map.confidence.items()
        ],
    }
