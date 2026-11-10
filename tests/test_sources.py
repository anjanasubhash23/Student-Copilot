import io
from pathlib import Path

import pymupdf
import pytest
from docx import Document
from pptx import Presentation
from pptx.util import Inches

from core.questions.excerpts import location
from core.sources import UnsupportedFileError, detect_kind, load_file
from core.sources.text import load_text
from core.sources.youtube import group_snippets, video_id


def _pdf(texts: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in texts:
        doc.new_page().insert_text((72, 72), text)
    return bytes(doc.tobytes())


def _pptx() -> bytes:
    prs = Presentation()
    for title in ("Keys", "Joins"):
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = title
        box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(5), Inches(1))
        box.text_frame.text = f"{title} body"
        slide.notes_slide.notes_text_frame.text = f"{title} notes"
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


def _docx() -> bytes:
    doc = Document()
    doc.add_paragraph("Intro text.")
    doc.add_heading("Normal Forms", level=1)
    doc.add_paragraph("1NF needs atomic values.")
    doc.add_heading("Indexes", level=1)
    doc.add_paragraph("B+ trees.")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def test_detects_kind_by_content_not_name() -> None:
    assert detect_kind(_pdf(["x"]), "notes.txt") == "pdf"
    assert detect_kind(_pptx(), "slides.pdf") == "pptx"
    assert detect_kind(_docx(), "x") == "docx"
    assert detect_kind(b"# Heading\nbody", "notes.md") == "text"


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"\x00\x01binary", "notes.md"),  # binary renamed to .md
        (b"plain text", "notes.exe"),  # text without a text extension
        (b"\xff\xfe\x00bad", "notes.txt"),  # not UTF-8
        (b"PK\x03\x04garbage", "x.docx"),  # damaged zip
    ],
)
def test_rejects_unsupported_files(data: bytes, name: str) -> None:
    with pytest.raises(UnsupportedFileError):
        detect_kind(data, name)


def test_loads_each_file_kind(tmp_path: Path) -> None:
    for name, data in {"a.pdf": _pdf(["Relational model", "SQL joins"]), "b.pptx": _pptx(), "c.docx": _docx()}.items():
        (tmp_path / name).write_bytes(data)
    pdf = load_file("pdf", tmp_path / "a.pdf")
    assert [(p.number, p.text.strip()) for p in pdf] == [(1, "Relational model"), (2, "SQL joins")]
    slides = load_file("pptx", tmp_path / "b.pptx")
    assert [p.number for p in slides] == [1, 2]
    assert "Keys body" in slides[0].text and "Keys notes" in slides[0].text
    sections = load_file("docx", tmp_path / "c.docx")
    assert [s.text.split("\n\n")[0] for s in sections] == ["Intro text.", "Normal Forms", "Indexes"]


def test_text_splits_on_markdown_headings() -> None:
    pages = load_text("Preface\n\n# One\nalpha\n## Two\nbeta\n")
    assert [p.text for p in pages] == ["Preface", "# One\nalpha", "## Two\nbeta"]
    assert load_text("") == []


@pytest.mark.parametrize(
    ("url", "vid"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?feature=share&v=dQw4w9WgXcQ&t=10", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ", None),
        ("https://example.com/watch?v=dQw4w9WgXcQ", None),
    ],
)
def test_video_id(url: str, vid: str | None) -> None:
    assert video_id(url) == vid


def test_transcript_grouped_into_timestamped_minutes() -> None:
    pages = group_snippets([(0.0, "hello"), (30.0, "there"), (61.5, "next  minute"), (130.0, "last")])
    assert [(p.number, p.timestamp, p.text) for p in pages] == [
        (1, 0.0, "hello there"),
        (2, 61.5, "next minute"),
        (3, 130.0, "last"),
    ]


def test_citation_locations() -> None:
    assert location({"kind": "pdf", "page_start": 4, "page_end": 4}) == "p. 4"
    assert location({"kind": "pdf", "page_start": 4, "page_end": 6}) == "pp. 4-6"
    assert location({"kind": "pptx", "page_start": 3, "page_end": 3}) == "slide 3"
    assert location({"kind": "docx", "page_start": 2, "page_end": 2}) == "section 2"
    assert location({"kind": "youtube", "timestamp": 725.0, "page_start": 1, "page_end": 1}) == "12:05"
    assert location({"kind": "youtube", "timestamp": 3725.0}) == "1:02:05"
