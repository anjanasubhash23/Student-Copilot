"""Topic recall and precision of an ingested graph against a corpus's labels.

python eval/run_eval.py data/cache/<space-id>.graph.json eval/data/dbms.topics.txt

The graph JSON is written by scripts/ingest.py. See eval/corpora.md for the label format.
Precision here is a lower bound: a real topic missing from the labels counts against it, so read the
"extra" list before trusting the number.
"""

import argparse
from pathlib import Path

from core.ingest.recall import parse_labels, score_topics
from core.ingest.schema import SpaceGraph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("graph", type=Path, help="graph JSON from scripts/ingest.py")
    parser.add_argument("labels", type=Path, help="label file, one topic per line")
    args = parser.parse_args()

    graph = SpaceGraph.model_validate_json(args.graph.read_text())
    labels = parse_labels(args.labels.read_text())
    score = score_topics(labels, graph.topics)

    print(f"sources:   {', '.join(s.name for s in graph.sources)}  ({graph.extracted_by.model})")
    print(f"recall:    {score.recall:.2f}  ({len(labels) - len(score.missed)}/{len(labels)} labels found)")
    print(f"precision: {score.precision:.2f}  ({len(graph.topics) - len(score.extra)}/{len(graph.topics)} topics)")
    if score.missed:
        print("\nmissed labels:\n" + "\n".join(f"  - {m}" for m in score.missed))
    if score.extra:
        print("\ntopics not in labels:\n" + "\n".join(f"  - {e}" for e in score.extra))


if __name__ == "__main__":
    main()
