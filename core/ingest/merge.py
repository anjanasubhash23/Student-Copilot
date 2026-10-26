"""Collapse the same topic extracted from different chunks into one."""

import re
from difflib import SequenceMatcher

from core.ingest.schema import Topic


def normalize(name: str) -> str:
    s = re.sub(r"\(.*?\)", "", name.lower())  # "Structured Query Language (SQL)" → "structured query language"
    s = re.sub(r"[^a-z0-9+ ]", " ", s)
    words = [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in s.split()]
    return " ".join(words)


def merge_topics(topics: list[Topic], threshold: float = 0.92) -> list[Topic]:
    merged: list[Topic] = []
    keys: list[str] = []
    for topic in topics:
        key = normalize(topic.name)
        match = next(
            (i for i, k in enumerate(keys) if k == key or SequenceMatcher(None, k, key).ratio() >= threshold),
            None,
        )
        if match is None:
            merged.append(topic.model_copy(deep=True))
            keys.append(key)
            continue
        kept = merged[match]
        kept.pages = sorted(set(kept.pages) | set(topic.pages))
        if topic.name != kept.name and topic.name not in kept.aliases:
            kept.aliases.append(topic.name)
        if len(topic.summary) > len(kept.summary):
            kept.summary = topic.summary
    return merged
