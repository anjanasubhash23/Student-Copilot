from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Chunk:
    page: int
    text: str


def read_pages(path: Path) -> list[str]:
    return [page.extract_text() or "" for page in PdfReader(path).pages]


def chunk_pages(pages: list[str], max_chars: int = 4000) -> list[Chunk]:
    """Pack paragraphs into chunks of up to max_chars, tagged with their starting page."""
    chunks: list[Chunk] = []
    buf, start = "", 1
    for page_no, text in enumerate(pages, start=1):
        for para in (p.strip() for p in text.split("\n\n")):
            if not para:
                continue
            if buf and len(buf) + len(para) > max_chars:
                chunks.append(Chunk(start, buf))
                buf = ""
            if not buf:
                start = page_no
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(Chunk(start, buf))
    return chunks
