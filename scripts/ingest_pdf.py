"""Ingest a course PDF into the topic graph.

    python scripts/ingest_pdf.py data/courses/dbms/notes.pdf --course dbms
    python scripts/ingest_pdf.py notes.pdf --course dbms --dry-run   # skip Neo4j
"""

import argparse
import logging
from pathlib import Path

from app.settings import get_settings
from core.graph import write_course_graph
from core.ingest.pipeline import build_course_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--course", required=True, help="course id, e.g. dbms")
    parser.add_argument("--dry-run", action="store_true", help="build the graph but don't write to Neo4j")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    graph = build_course_graph(args.course, args.pdf)

    out = get_settings().cache_dir / f"{args.course}.graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(graph.model_dump_json(indent=2))
    print(f"graph JSON → {out}")

    if not args.dry_run:
        write_course_graph(graph)
        print(f"wrote course '{args.course}' to Neo4j")


if __name__ == "__main__":
    main()
