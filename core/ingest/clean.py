"""Strip PDF noise: running headers/footers, page numbers, hyphenated line breaks."""

import re
from collections import Counter

from core.ingest.schema import Page

PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(/|of)\s*\d+)?$", re.IGNORECASE)
EDGE_LINES = 2  # headers/footers live in the first/last few lines of a page


def _key(line: str) -> str:
    return re.sub(r"\d+", "#", line.lower())


def _edges(lines: list[str]) -> list[str]:
    content = [l for l in lines if l]
    return content[:EDGE_LINES] + content[-EDGE_LINES:]


def _boilerplate(pages: list[list[str]]) -> set[str]:
    """Edge lines repeated on at least half the pages (digits ignored, so 'Lecture 3' matches 'Lecture 4')."""
    if len(pages) < 3:
        return set()
    counts = Counter()
    for lines in pages:
        counts.update({_key(l) for l in _edges(lines) if len(l) <= 80})
    return {k for k, c in counts.items() if c >= len(pages) / 2}


def clean_pages(pages: list[Page]) -> list[Page]:
    split = [[l.strip() for l in p.text.splitlines()] for p in pages]
    boiler = _boilerplate(split)
    out = []
    for page, lines in zip(pages, split):
        edges = set(_edges(lines))
        kept = [l for l in lines if not PAGE_NUMBER.match(l) and not (l in edges and _key(l) in boiler)]
        text = "\n".join(kept)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        out.append(Page(number=page.number, text=text))
    return out
