"""Stable node ids: `{space_id}:{slug}` for topics and units, `{space_id}:{source_id}:{n}` for chunks."""

import re
import unicodedata


def slugify(name: str) -> str:
    """'B+ Tree' → 'b-plus-tree', 'Third Normal Form (3NF)' → 'third-normal-form-3nf'.

    '+' and '#' are spelled out so that 'B+ Tree' and 'B Tree', or 'C#' and 'C', stay distinct.
    """
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("+", " plus ").replace("#", " sharp ")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "untitled"


def assign_ids(space_id: str, names: list[str]) -> dict[str, str]:
    """Map each distinct name to an id unique within the space; slug clashes get -2, -3, ... in input order."""
    ids: dict[str, str] = {}
    used: set[str] = set()
    for name in names:
        if name in ids:
            continue
        base = slugify(name)
        slug, n = base, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        ids[name] = f"{space_id}:{slug}"
    return ids


def chunk_id(space_id: str, source_id: str, index: int) -> str:
    return f"{space_id}:{source_id}:{index}"
