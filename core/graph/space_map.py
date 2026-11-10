"""An in-memory copy of a space's topics and prerequisite edges.

Loaded once per request from Neo4j (core.graph.queries.get_space_map). Mastery propagation, topic selection
and the map view all work on it, which keeps that logic pure and testable without a database.
"""

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TopicInfo:
    id: str
    name: str
    summary: str = ""
    first_seen: int = 0
    unit_id: str | None = None
    unit: str | None = None
    unit_order: int = 0
    position: int = 0


@dataclass
class SpaceMap:
    topics: dict[str, TopicInfo]
    # topic id → ids of its direct prerequisites / of the topics that directly build on it
    prereqs: dict[str, set[str]] = field(default_factory=dict)
    dependents: dict[str, set[str]] = field(default_factory=dict)
    confidence: dict[tuple[str, str], float] = field(default_factory=dict)

    @classmethod
    def build(cls, topics: list[TopicInfo], edges: list[tuple[str, str, float]]) -> "SpaceMap":
        """`edges` are (prerequisite, dependent, confidence), the direction of PREREQUISITE_OF."""
        m = cls(topics={t.id: t for t in topics})
        m.prereqs = {t.id: set() for t in topics}
        m.dependents = {t.id: set() for t in topics}
        for pre, dep, conf in edges:
            if pre in m.topics and dep in m.topics:
                m.prereqs[dep].add(pre)
                m.dependents[pre].add(dep)
                m.confidence[(pre, dep)] = conf
        return m

    def ancestors(self, topic_id: str, max_hops: int | None = None) -> dict[str, int]:
        """Transitive prerequisites → hops from `topic_id` (shortest)."""
        return self._walk(topic_id, self.prereqs, max_hops)

    def descendants(self, topic_id: str, max_hops: int | None = None) -> dict[str, int]:
        """Topics that transitively build on `topic_id` → hops (shortest)."""
        return self._walk(topic_id, self.dependents, max_hops)

    @staticmethod
    def _walk(start: str, edges: dict[str, set[str]], max_hops: int | None) -> dict[str, int]:
        seen: dict[str, int] = {}
        queue = deque([(start, 0)])
        while queue:
            node, hops = queue.popleft()
            if max_hops is not None and hops >= max_hops:
                continue
            for nxt in sorted(edges.get(node, ())):
                if nxt != start and nxt not in seen:
                    seen[nxt] = hops + 1
                    queue.append((nxt, hops + 1))
        return seen
