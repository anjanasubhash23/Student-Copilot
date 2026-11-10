"""Which topic to ask about next."""

from core.graph.space_map import SpaceMap
from core.mastery.bkt import MASTERED, PRIOR

READY = 0.6  # a topic is ready to practise when all its prerequisites are at least this likely known


def pick_diagnostic_topic(space: SpaceMap, mastery: dict[str, float], asked: set[str]) -> str | None:
    """The unasked topic whose answer tells us most: uncertain (p near 0.5) and connected to many others,
    since propagation spreads its answer to its prerequisites (if right) or dependents (if wrong).
    Ties go to topics with both, whose answer informs the map either way."""
    best: tuple[float, int, int, str] | None = None
    for tid, info in space.topics.items():
        if tid in asked:
            continue
        p = mastery.get(tid, PRIOR)
        up, down = len(space.ancestors(tid, 3)), len(space.descendants(tid, 3))
        key = (p * (1 - p) * (1 + up + down), min(up, down), -info.first_seen, tid)
        if best is None or key > best:
            best = key
    return best[-1] if best else None


def pick_practice_topic(space: SpaceMap, mastery: dict[str, float], avoid: set[str] | None = None) -> str | None:
    """The weakest unmastered topic whose prerequisites are ready; else the weakest unmastered topic.

    `avoid` (e.g. the topic just practised) is skipped unless nothing else is left.
    """
    avoid = avoid or set()

    def p(tid: str) -> float:
        return mastery.get(tid, PRIOR)

    def order(tid: str) -> tuple[float, int, int, str]:
        info = space.topics[tid]
        return (p(tid), info.unit_order, info.first_seen, tid)

    open_topics = [t for t in space.topics if p(t) < MASTERED]
    for pool in ([t for t in open_topics if t not in avoid], open_topics):
        ready = [t for t in pool if all(p(pre) >= READY for pre in space.prereqs.get(t, ()))]
        for candidates in (ready, pool):
            if candidates:
                return min(candidates, key=order)
    return None
