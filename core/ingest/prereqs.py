from collections import defaultdict

from core.ingest.schema import Prereq, PrereqsOut, Topic, Unit
from core.llm import load_prompt, structured


def extract_prereqs(topics: list[Topic], units: list[Unit]) -> list[Prereq]:
    summaries = {t.name: t.summary for t in topics}
    listing = "\n\n".join(
        f"## Unit {u.order}: {u.name}\n" + "\n".join(f"- {n}: {summaries[n]}" for n in u.topics) for u in units
    )
    out = structured(load_prompt("prereqs", topics=listing), PrereqsOut)
    return validate_prereqs(out.edges, set(summaries))


def validate_prereqs(edges: list[Prereq], names: set[str]) -> list[Prereq]:
    """Drop edges to unknown topics, self-loops, duplicates, and any edge that would close a cycle."""
    graph: dict[str, set[str]] = defaultdict(set)
    kept = []
    for edge in edges:
        if edge.topic not in names or edge.requires not in names or edge.topic == edge.requires:
            continue
        if edge.requires in graph[edge.topic] or _reachable(graph, edge.requires, edge.topic):
            continue
        graph[edge.topic].add(edge.requires)
        kept.append(edge)
    return kept


def _reachable(graph: dict[str, set[str]], start: str, target: str) -> bool:
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(graph[node])
    return False
