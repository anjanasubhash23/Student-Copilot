"""Ingest a PDF into a study space's topic graph.

python scripts/ingest_pdf.py notes.pdf --new-space "Semester 5 DBMS"   # creates the space, prints its id
python scripts/ingest_pdf.py notes.pdf --space <space-id>              # re-ingest into an existing space
python scripts/ingest_pdf.py notes.pdf --space <space-id> --dry-run    # skip Neo4j

Re-ingesting replaces the space's graph. The graph is also saved as data/cache/<space-id>.graph.json.
"""

import argparse
import logging
import sys
from contextlib import closing
from pathlib import Path

from app.settings import get_settings
from core.graph import write_space_graph
from core.ingest.pipeline import build_space_graph
from core.spaces import StudySpace
from core.storage import sqlite
from core.storage.spaces import SqliteStudySpaceRepository


def resolve_space(args: argparse.Namespace) -> StudySpace:
    settings = get_settings()
    with closing(sqlite.connect(settings.sqlite_path)) as conn:
        sqlite.migrate(conn)
        repo = SqliteStudySpaceRepository(conn)
        if args.new_space:
            space = StudySpace.new(args.new_space)
            repo.add(space)
            print(f"created study space '{space.name}' (id {space.id})")
            return space
        found = repo.get(args.space)
        if found is None:
            known = "\n".join(f"  {s.id}  {s.name}" for s in repo.list_all()) or "  (none)"
            sys.exit(f"no study space with id {args.space!r}. Known spaces:\n{known}")
        return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--space", help="id of an existing study space")
    target.add_argument("--new-space", metavar="NAME", help="create a study space with this name")
    parser.add_argument("--dry-run", action="store_true", help="build the graph but don't write to Neo4j")
    args = parser.parse_args()

    if not args.pdf.is_file():
        sys.exit(f"not a file: {args.pdf}")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    space = resolve_space(args)
    graph = build_space_graph(space.id, args.pdf)

    out = get_settings().cache_dir / f"{space.id}.graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(graph.model_dump_json(indent=2))
    print(f"graph JSON → {out}")

    if not args.dry_run:
        write_space_graph(graph)
        print(f"wrote {len(graph.topics)} topics to Neo4j for space '{space.name}'")


if __name__ == "__main__":
    main()
