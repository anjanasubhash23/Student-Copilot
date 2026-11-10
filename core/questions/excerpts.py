"""Quote source chunks into prompts inside delimiters, so they read as content and can't close the tag."""

import re
from typing import Any

MAX_CHARS = 4000
LOOKALIKE = "\u2039"  # ‹ : reads like "<" to the model but can't close a tag  # noqa: RUF003


def neutralize(text: str, tag: str) -> str:
    return re.sub(rf"<\s*/?\s*{tag}\b", lambda m: m.group(0).replace("<", LOOKALIKE), text, flags=re.IGNORECASE)


def format_excerpts(chunks: list[dict[str, Any]], tag: str = "excerpt") -> str:
    return "\n\n".join(
        f'<{tag} n="{i}">\n{neutralize(c["text"][:MAX_CHARS], tag)}\n</{tag}>' for i, c in enumerate(chunks, start=1)
    )


def location(chunk: dict[str, Any]) -> str:
    """Where a chunk is in its source, for citations: 'p. 4', 'slides 3-4', 'section 2', '12:05'."""
    kind = chunk.get("kind")
    if kind == "youtube" and chunk.get("timestamp") is not None:
        seconds = int(chunk["timestamp"])
        return (
            f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
            if seconds >= 3600
            else (f"{seconds // 60}:{seconds % 60:02d}")
        )
    start, end = chunk.get("page_start"), chunk.get("page_end")
    if start is None:
        return ""
    word = {"pdf": ("p.", "pp."), "pptx": ("slide", "slides")}.get(kind or "", ("section", "sections"))
    return f"{word[0]} {start}" if start == end or end is None else f"{word[1]} {start}-{end}"
