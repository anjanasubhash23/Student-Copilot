"""Add a file or link to a study space and ingest it now, without the API.

python scripts/ingest.py notes.pdf --new-space "Semester 5 DBMS" --owner you@example.com
python scripts/ingest.py https://youtu.be/VIDEO_ID --space <space-id>
python scripts/ingest.py notes.pdf --dry-run      # build the graph JSON only; no database is touched

Runs the same jobs the API's worker would (ingest the source, then rebuild the space's graph), then
saves the graph as data/cache/<space-id>.graph.json. --owner makes the space visible in the web app.
"""

import argparse
import hashlib
import logging
import sys
from contextlib import closing
from pathlib import Path

from app.settings import get_settings
from core.graph.client import create_driver
from core.ingest.pipeline import build_space_graph, extract_source
from core.ingest.schema import SourceRef
from core.sources import EXTENSIONS, detect_kind, is_youtube, load_file, load_web, load_youtube
from core.spaces import StudySpace
from core.storage import sqlite
from core.storage.files import FileStore
from core.storage.jobs import SqliteJobQueue
from core.storage.sources import Source, SqliteSourceRepository
from core.storage.spaces import SqliteStudySpaceRepository
from core.storage.users import SqliteUserRepository
from workers.run import run_one
from workers.tasks import Context


def _source_for(target: str, space_id: str, files: FileStore) -> Source:
    if target.startswith(("http://", "https://")):
        return Source.new(space_id, "youtube" if is_youtube(target) else "web", target[:200], uri=target)
    path = Path(target)
    if not path.is_file():
        sys.exit(f"not a file or link: {target}")
    data = path.read_bytes()
    kind = detect_kind(data, path.name)
    source = Source.new(space_id, kind, path.name, content_hash=hashlib.sha256(data).hexdigest())
    stored = files.save_upload(space_id, source.id, EXTENSIONS[kind], data)
    return source.model_copy(update={"storage_path": str(stored)})


def dry_run(target: str) -> None:
    settings = get_settings()
    if target.startswith(("http://", "https://")):
        kind = "youtube" if is_youtube(target) else "web"
        pages = load_youtube(target) if kind == "youtube" else load_web(target, settings.max_fetch_mb * 1_000_000)[0]
        name = target
    else:
        path = Path(target)
        kind = detect_kind(path.read_bytes(), path.name)
        pages, name = load_file(kind, path, settings.ocr_lang), path.name
    source_id = hashlib.sha256(target.encode()).hexdigest()[:16]
    extraction = extract_source(SourceRef(id=source_id, name=name, kind=kind), pages)
    graph = build_space_graph(f"dry-run-{source_id}", [extraction])
    out = settings.cache_dir / f"{graph.space_id}.graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(graph.model_dump_json(indent=2))
    print(f"{len(graph.topics)} topics, {len(graph.units)} units, {len(graph.prereqs)} prerequisite edges")
    print(f"graph JSON → {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="a file (PDF, PPTX, DOCX, MD, TXT) or a web/YouTube link")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--space", help="id of an existing study space")
    target.add_argument("--new-space", metavar="NAME", help="create a study space with this name")
    parser.add_argument("--owner", metavar="EMAIL", help="with --new-space: the account that owns the space")
    parser.add_argument("--dry-run", action="store_true", help="only build the graph JSON; no SQLite or Neo4j")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.dry_run:
        dry_run(args.target)
        return
    if not (args.space or args.new_space):
        parser.error("give --space or --new-space (or --dry-run)")

    settings = get_settings()
    files = FileStore(settings.data_dir)
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        sqlite.migrate(conn)
        spaces = SqliteStudySpaceRepository(conn)
        if args.new_space:
            owner = SqliteUserRepository(conn).get_by_email(args.owner) if args.owner else None
            if args.owner and owner is None:
                sys.exit(f"no account with email {args.owner}; register in the web app first")
            space = StudySpace.new(args.new_space, owner_id=owner.id if owner else None)
            spaces.add(space)
            print(f"created study space '{space.name}' (id {space.id})")
        else:
            found = spaces.get(args.space)
            if found is None:
                known = "\n".join(f"  {s.id}  {s.name}" for s in spaces.list_all()) or "  (none)"
                sys.exit(f"no study space with id {args.space!r}. Known spaces:\n{known}")
            space = found

        source = _source_for(args.target, space.id, files)
        SqliteSourceRepository(conn).add(source)
        queue = SqliteJobQueue(conn)
        queue.enqueue("ingest_source", space.id, source.id)

        driver = create_driver(settings)
        try:
            ctx = Context(settings=settings, conn=conn, driver=driver)
            while run_one(ctx, queue):  # drains the queue: this source, then the graph rebuild
                pass
        finally:
            driver.close()
        done = SqliteSourceRepository(conn).get(source.id)
        space = spaces.get(space.id) or space
    if done and done.status == "failed":
        sys.exit(f"ingesting {done.name} failed: {done.error}")
    print(
        f"space '{space.name}': map {space.graph_status}; graph JSON → {settings.cache_dir / f'{space.id}.graph.json'}"
    )


if __name__ == "__main__":
    main()
