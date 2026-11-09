"""Score extracted topics against a hand-made label list (e.g. a course's table of contents).

Label file: one topic per line; `|` separates accepted names for the same topic; `#` starts a comment.

    Third Normal Form | 3NF
    B+ Tree
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

from core.ingest.merge import normalize
from core.ingest.schema import Topic

MATCH_RATIO = 0.85  # looser than merge's 0.92: here a near-miss name still means the topic was found


@dataclass
class TopicScore:
    recall: float  # share of labels found among the topics
    precision: float  # share of topics that match some label
    missed: list[str]  # labels no topic matched
    extra: list[str]  # topics no label matched


def parse_labels(text: str) -> list[list[str]]:
    labels = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            labels.append([name.strip() for name in line.split("|") if name.strip()])
    return labels


def _matches(a: str, b: str) -> bool:
    return a == b or SequenceMatcher(None, a, b).ratio() >= MATCH_RATIO


def score_topics(labels: list[list[str]], topics: list[Topic]) -> TopicScore:
    topic_keys = [{normalize(n) for n in [t.name, *t.aliases]} for t in topics]
    matched_topics: set[int] = set()
    missed = []
    for names in labels:
        keys = {normalize(n) for n in names}
        hits = {i for i, tk in enumerate(topic_keys) if any(_matches(k, t) for k in keys for t in tk)}
        if hits:
            matched_topics |= hits
        else:
            missed.append(names[0])
    return TopicScore(
        recall=(len(labels) - len(missed)) / len(labels) if labels else 0.0,
        precision=len(matched_topics) / len(topics) if topics else 0.0,
        missed=missed,
        extra=[t.name for i, t in enumerate(topics) if i not in matched_topics],
    )
