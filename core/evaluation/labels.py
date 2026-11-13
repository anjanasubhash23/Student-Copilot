"""Hand-labelled evaluation (spec section 11).

The export step writes CSVs with an empty verdict column; a person fills it in with y/n; the score step reads
them back. Rows left blank are skipped, so a half-labelled file still gives a (smaller-sample) number.
"""

import csv
import io
import random
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from core.ingest.merge import normalize
from core.ingest.schema import SpaceGraph

YES = {"y", "yes", "1", "true", "ok", "✓"}
NO = {"n", "no", "0", "false", "x", "✗"}

EDGE_FIELDS = ["requires", "topic", "reason", "confidence", "correct"]
MERGE_FIELDS = ["a", "b", "predicted_same", "same"]
QUESTION_FIELDS = ["id", "topic", "type", "status", "stem", "options", "answer", "source_excerpt", "correct"]


def verdict(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    return True if v in YES else False if v in NO else None


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


# Export


def sample_edges(graph: SpaceGraph, n: int = 40, seed: int = 1) -> list[dict[str, Any]]:
    """Up to `n` prerequisite edges, chosen at random, to judge "is this a real prerequisite?"."""
    edges = random.Random(seed).sample(graph.prereqs, min(n, len(graph.prereqs)))
    return [
        {"requires": e.requires, "topic": e.topic, "reason": e.reason, "confidence": e.confidence, "correct": ""}
        for e in edges
    ]


def sample_merges(graph: SpaceGraph, n: int = 30, seed: int = 1, near: float = 0.6) -> list[dict[str, Any]]:
    """Pairs to judge "are these the same topic?": up to `n` the pipeline merged (a topic and an alias), and up
    to `n` it kept apart although their names are similar (the cases most likely to be missed duplicates)."""
    rng = random.Random(seed)
    merged = [(t.name, alias) for t in graph.topics for alias in t.aliases]
    names = [t.name for t in graph.topics]
    keys = [normalize(n) for n in names]
    near_pairs = [
        (names[i], names[j], ratio)
        for i in range(len(names))
        for j in range(i + 1, len(names))
        if (ratio := SequenceMatcher(None, keys[i], keys[j]).ratio()) >= near
    ]
    near_pairs.sort(key=lambda p: -p[2])
    rows = [{"a": a, "b": b, "predicted_same": "y", "same": ""} for a, b in rng.sample(merged, min(n, len(merged)))]
    rows += [{"a": a, "b": b, "predicted_same": "n", "same": ""} for a, b, _ in near_pairs[:n]]
    return rows


# Scoring


@dataclass
class Rate:
    hits: int
    total: int

    @property
    def value(self) -> float | None:
        return self.hits / self.total if self.total else None

    def __str__(self) -> str:
        return f"{self.value:.2f} ({self.hits}/{self.total})" if self.total else "- (nothing labelled)"


def edge_precision(rows: list[dict[str, str]]) -> Rate:
    judged = [v for r in rows if (v := verdict(r.get("correct"))) is not None]
    return Rate(sum(judged), len(judged))


def merge_scores(rows: list[dict[str, str]]) -> tuple[Rate, Rate]:
    """(precision, recall) of the merge step: of the pairs it merged, how many are the same topic; of the
    labelled same-topic pairs, how many it merged."""
    labelled = [
        (p, s)
        for r in rows
        if (p := verdict(r.get("predicted_same"))) is not None and (s := verdict(r.get("same"))) is not None
    ]
    merged = [s for p, s in labelled if p]
    same = [p for p, s in labelled if s]
    return Rate(sum(merged), len(merged)), Rate(sum(same), len(same))


def question_validity(rows: list[dict[str, str]]) -> tuple[Rate, Rate]:
    """(validity of kept questions, validator agreement): the share of questions the app kept (status 'valid')
    that a person judged correct, and the share of all judged questions where the validator's keep/reject
    decision matched the person's."""
    judged = [(r.get("status") == "valid", v) for r in rows if (v := verdict(r.get("correct"))) is not None]
    kept = [v for valid, v in judged if valid]
    agree = [valid == v for valid, v in judged]
    return Rate(sum(kept), len(kept)), Rate(sum(agree), len(agree))
