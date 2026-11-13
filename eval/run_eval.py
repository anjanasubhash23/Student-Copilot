"""The evaluation suite (spec section 11). Each subcommand prints its numbers and a Markdown row to paste
into the results table in eval/corpora.md.

Automatic (no labelling):
  simulate                        diagnostic accuracy and mastery-model AUC on simulated learners
  simulate --graph G.json         ...on the structure of a real ingested map
  ingest [--space ID]             time and LLM usage per ingested source

Against hand labels (see eval/corpora.md for the workflow):
  topics GRAPH LABELS.txt         topic recall/precision vs a table of contents
  export --space ID --corpus NAME write CSVs to label: prerequisite edges, merges, questions
  edges CSV                       prerequisite edge precision
  merges CSV                      duplicate-merge precision/recall
  questions CSV                   question validity and validator agreement
"""

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from app.settings import get_settings
from core.evaluation.labels import (
    EDGE_FIELDS,
    MERGE_FIELDS,
    QUESTION_FIELDS,
    edge_precision,
    merge_scores,
    question_validity,
    read_csv,
    sample_edges,
    sample_merges,
    write_csv,
)
from core.evaluation.report import ingest_report
from core.graph.ids import assign_ids
from core.ingest.recall import parse_labels, score_topics
from core.ingest.schema import SpaceGraph
from core.mastery.simulate import simulate
from core.storage import sqlite
from core.storage.learning import SqliteQuestionRepository

# Spec targets, and floors below which CI fails (a regression, not a target).
DIAGNOSTIC_TARGET = 0.70
AUC_TARGET = 0.75
AUC_FLOOR = 0.60


def _graph(path: Path) -> SpaceGraph:
    return SpaceGraph.model_validate_json(path.read_text())


def cmd_simulate(args: argparse.Namespace) -> int:
    graph = _graph(args.graph) if args.graph else None
    r = simulate(learners=args.learners, seed=args.seed, graph=graph)
    where = f"map from {args.graph.name}" if graph else "random course-like maps"
    print(f"{r.learners} simulated learners on {where} ({r.topics:.0f} topics, {r.known_share:.0%} known on average)")
    print(f"diagnostic accuracy:          {r.diagnostic_accuracy:.3f}   target ≥ {DIAGNOSTIC_TARGET}")
    print(f"  balanced accuracy:          {r.diagnostic_balanced_accuracy:.3f}")
    print(f"  without propagation:        {r.without_propagation:.3f}")
    print(f"  without starting estimates: {r.without_estimates:.3f}")
    print(f"  guess 'unknown' for all:    {r.baseline_all_unknown:.3f}")
    print(f"mastery-model AUC:            {r.auc:.3f}   target ≥ {AUC_TARGET}  ({r.answers} practice answers)")
    print(f"  true-state ceiling:         {r.oracle_auc:.3f}")
    print(
        f"\n| simulated ({where}) | {r.learners} learners | diagnostic {r.diagnostic_accuracy:.2f} "
        f"(baseline {r.baseline_all_unknown:.2f}) | AUC {r.auc:.2f} (ceiling {r.oracle_auc:.2f}) |"
    )
    if args.check:
        failures = []
        if r.diagnostic_accuracy < DIAGNOSTIC_TARGET:
            failures.append(f"diagnostic accuracy {r.diagnostic_accuracy:.3f} < {DIAGNOSTIC_TARGET}")
        if r.diagnostic_accuracy <= r.baseline_all_unknown:
            failures.append("diagnostic doesn't beat guessing 'unknown' for everything")
        if r.auc < AUC_FLOOR:
            failures.append(f"AUC {r.auc:.3f} < regression floor {AUC_FLOOR}")
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1 if failures else 0
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    settings = get_settings()
    with closing(sqlite.connect(settings.sqlite_path, create=False)) as conn:
        rows = ingest_report(conn, args.space)
    if not rows:
        print("no ingested sources yet")
        return 0
    print("| space | source | kind | pages | time | per 100 pages | LLM calls (cached) | tokens in/out | model |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        per100 = f"{r.seconds_per_100_pages / 60:.1f} min" if r.seconds_per_100_pages else "-"
        print(
            f"| {r.space} | {r.source} | {r.kind} | {r.pages} | {r.seconds / 60:.1f} min | {per100} | "
            f"{r.llm_calls} ({r.llm_cached}) | {r.input_tokens}/{r.output_tokens} | {r.model} |"
        )
    print("\nTimes include LLM-cache hits; re-ingested sources look faster than a first run.")
    return 0


def cmd_topics(args: argparse.Namespace) -> int:
    graph = _graph(args.graph)
    labels = parse_labels(args.labels.read_text())
    score = score_topics(labels, graph.topics)
    print(f"sources:   {', '.join(s.name for s in graph.sources)}  ({graph.extracted_by.model})")
    print(f"recall:    {score.recall:.2f}  ({len(labels) - len(score.missed)}/{len(labels)} labels found)")
    print(f"precision: {score.precision:.2f}  ({len(graph.topics) - len(score.extra)}/{len(graph.topics)} topics)")
    if score.missed:
        print("\nmissed labels:\n" + "\n".join(f"  - {m}" for m in score.missed))
    if score.extra:
        print("\ntopics not in labels:\n" + "\n".join(f"  - {e}" for e in score.extra))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    settings = get_settings()
    graph_path = settings.cache_dir / f"{args.space}.graph.json"
    if not graph_path.exists():
        print(f"no graph JSON at {graph_path}; ingest a source into that space first", file=sys.stderr)
        return 1
    graph = _graph(graph_path)
    out = Path(args.out) / args.corpus
    write_csv(out.with_suffix(".edges.csv"), EDGE_FIELDS, sample_edges(graph, args.edges))
    write_csv(out.with_suffix(".merges.csv"), MERGE_FIELDS, sample_merges(graph, args.merges))
    chunks = {f"{graph.space_id}:{c.key}": c.text for c in graph.chunks}
    names = {v: k for k, v in assign_ids(graph.space_id, [t.name for t in graph.topics]).items()}
    with closing(sqlite.connect(settings.sqlite_path, create=False)) as conn:
        rows = conn.execute("SELECT id FROM questions WHERE space_id = ? ORDER BY created_at", (args.space,)).fetchall()
        repo = SqliteQuestionRepository(conn)
        questions = [q for r in rows if (q := repo.get(r["id"])) is not None][: args.questions]
    write_csv(
        out.with_suffix(".questions.csv"),
        QUESTION_FIELDS,
        [
            {
                "id": q.id,
                "topic": names.get(q.topic_id, q.topic_id),
                "type": q.type,
                "status": q.status,
                "stem": q.stem,
                "options": json.dumps(
                    [f"{'*' if i in q.correct else ''}{o}" for i, o in enumerate(q.options)], ensure_ascii=False
                ),
                "answer": q.answer if q.type != "numeric" else f"{q.answer} [{q.num_low}, {q.num_high}]",
                "source_excerpt": chunks.get(q.chunk_id, "")[:600],
                "correct": "",
            }
            for q in questions
        ],
    )
    print(f"wrote {out}.edges.csv, {out}.merges.csv, {out}.questions.csv")
    print("Fill in the last column of each with y or n, then run the edges / merges / questions commands.")
    return 0


def cmd_edges(args: argparse.Namespace) -> int:
    p = edge_precision(read_csv(args.csv.read_text()))
    print(f"prerequisite edge precision: {p}   target ≥ 0.80")
    return 0


def cmd_merges(args: argparse.Namespace) -> int:
    precision, recall = merge_scores(read_csv(args.csv.read_text()))
    print(f"merge precision: {precision}   target ≥ 0.90")
    print(f"merge recall:    {recall}   target ≥ 0.80")
    return 0


def cmd_questions(args: argparse.Namespace) -> int:
    validity, agreement = question_validity(read_csv(args.csv.read_text()))
    print(f"kept questions judged correct: {validity}   target ≥ 0.90")
    print(f"validator agrees with you:     {agreement}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("simulate", help="diagnostic accuracy and AUC on simulated learners")
    p.add_argument("--graph", type=Path, help="simulate on this ingested graph JSON's structure")
    p.add_argument("--learners", type=int, default=200)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--check", action="store_true", help="exit 1 below the diagnostic target or the AUC floor")
    p.set_defaults(fn=cmd_simulate)

    p = sub.add_parser("ingest", help="time and LLM usage per ingested source")
    p.add_argument("--space", help="only this space")
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("topics", help="topic recall/precision against labels")
    p.add_argument("graph", type=Path)
    p.add_argument("labels", type=Path)
    p.set_defaults(fn=cmd_topics)

    p = sub.add_parser("export", help="write CSVs to label for a space")
    p.add_argument("--space", required=True)
    p.add_argument("--corpus", required=True, help="name for the files, e.g. dbms")
    p.add_argument("--out", default="eval/data")
    p.add_argument("--edges", type=int, default=40)
    p.add_argument("--merges", type=int, default=30, help="pairs of each kind (merged / kept apart)")
    p.add_argument("--questions", type=int, default=50)
    p.set_defaults(fn=cmd_export)

    for name, fn in (("edges", cmd_edges), ("merges", cmd_merges), ("questions", cmd_questions)):
        p = sub.add_parser(name, help=f"score a labelled {name} CSV")
        p.add_argument("csv", type=Path)
        p.set_defaults(fn=fn)

    args = parser.parse_args()
    result: int = args.fn(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
