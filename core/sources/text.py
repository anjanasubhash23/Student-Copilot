"""Markdown and plain text → Pages, one per heading section (the whole file if it has no headings)."""

import re

from core.ingest.schema import Page

HEADING = re.compile(r"^#{1,6}\s+\S")


def load_text(text: str) -> list[Page]:
    sections: list[list[str]] = [[]]
    for line in text.splitlines():
        if HEADING.match(line) and any(s.strip() for s in sections[-1]):
            sections.append([])
        sections[-1].append(line)
    pages = ["\n".join(s).strip() for s in sections]
    return [Page(number=i, text=p) for i, p in enumerate((p for p in pages if p), start=1)]
