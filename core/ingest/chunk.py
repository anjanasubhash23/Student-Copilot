"""Pack paragraphs into overlapping chunks that remember which pages they came from."""

from core.ingest.schema import Chunk, Page


def _split_long(text: str, max_chars: int) -> list[str]:
    pieces, buf = [], ""
    for word in text.split(" "):
        if buf and len(buf) + len(word) + 1 > max_chars:
            pieces.append(buf)
            buf = ""
        buf = f"{buf} {word}" if buf else word
    if buf:
        pieces.append(buf)
    return pieces


def _make(chunk_id: int, paras: list[tuple[int, str]]) -> Chunk:
    return Chunk(
        id=chunk_id,
        page_start=paras[0][0],
        page_end=paras[-1][0],
        text="\n\n".join(t for _, t in paras),
    )


def chunk_pages(pages: list[Page], max_chars: int = 6000, overlap: int = 500) -> list[Chunk]:
    paras = [
        (p.number, piece)
        for p in pages
        for para in p.text.split("\n\n")
        if para.strip()
        for piece in _split_long(para.strip(), max_chars)
    ]

    chunks: list[Chunk] = []
    current: list[tuple[int, str]] = []
    size = 0
    for page, text in paras:
        if current and size + len(text) > max_chars:
            chunks.append(_make(len(chunks), current))
            # carry trailing paragraphs into the next chunk so topics spanning a boundary aren't lost
            tail: list[tuple[int, str]] = []
            tail_size = 0
            for item in reversed(current):
                if tail_size + len(item[1]) > overlap:
                    break
                tail.insert(0, item)
                tail_size += len(item[1])
            current, size = tail, tail_size
        current.append((page, text))
        size += len(text)
    if current:
        chunks.append(_make(len(chunks), current))
    return chunks
