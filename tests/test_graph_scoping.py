"""Engineering rule: every Neo4j query is scoped to one study space.

Finds every Cypher string (plain or f-string) passed to `.run(...)` in core/graph and checks that it uses `$space_id`,
that the call passes `space_id=`, and that every labelled node pattern is filtered on the space,
either inline (`{space_id: $space_id}`) or in a WHERE (`n.space_id = $space_id`).
"""

import ast
import re
from pathlib import Path

import pytest

GRAPH_DIR = Path(__file__).resolve().parent.parent / "core" / "graph"
NODE = re.compile(r"\((\w*):(\w+)\s*(\{[^}]*\})?\)")


def _cypher_calls() -> list[tuple[str, ast.Call, str]]:
    calls = []
    for path in sorted(GRAPH_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run":
                query = _literal(node.args[0]) if node.args else None
                if query is not None:
                    calls.append((f"{path.name}:{node.lineno}", node, query))
    return calls


def _literal(arg: ast.expr) -> str | None:
    """The query text; an f-string's {...} parts become a placeholder (they only interpolate field lists)."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr):
        return "".join(str(v.value) if isinstance(v, ast.Constant) else "<fields>" for v in arg.values)
    return None


def _unscoped(query: str) -> list[str]:
    """Labelled node patterns in `query` that aren't filtered on $space_id."""
    bad = []
    for var, label, props in NODE.findall(query):
        inline = props and re.search(r"space_id:\s*\$space_id", props)
        in_where = var and re.search(rf"\b{var}\.space_id\s*=\s*\$space_id", query)
        if not (inline or in_where):
            bad.append(f"({var}:{label})")
    return bad


CALLS = _cypher_calls()


def test_finds_queries() -> None:
    # Guard against the scan silently matching nothing after a refactor.
    assert len(CALLS) >= 10


@pytest.mark.parametrize(("where", "call", "query"), CALLS, ids=[c[0] for c in CALLS])
def test_query_is_space_scoped(where: str, call: ast.Call, query: str) -> None:
    assert "$space_id" in query, f"{where}: query doesn't use $space_id"
    assert any(kw.arg == "space_id" for kw in call.keywords), f"{where}: call doesn't pass space_id="
    assert _unscoped(query) == [], f"{where}: not filtered on space_id"


def test_check_catches_unscoped_patterns() -> None:
    assert _unscoped("MATCH (t:Topic {space_id: $space_id})-[:PREREQUISITE_OF]->(d:Topic) RETURN d") == ["(d:Topic)"]
    assert _unscoped("MATCH (n:Topic) WHERE n.space_id = $space_id RETURN n") == []
    assert _unscoped("MATCH (:Unit {name: $name}) RETURN 1") == ["(:Unit)"]
