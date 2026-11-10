"""PowerPoint and Word documents → Pages.

A slide is a page (slide text, then speaker notes). Word files have no pages, so each section that starts
at a heading is one; citations then read "section N".
"""

from pathlib import Path

from core.ingest.schema import Page


def load_pptx(path: Path) -> list[Page]:
    from pptx import Presentation

    pages = []
    for i, slide in enumerate(Presentation(str(path)).slides, start=1):
        lines: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                lines.extend(p.text for p in shape.text_frame.paragraphs if p.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    lines.append(" | ".join(cell.text for cell in row.cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(notes)
        pages.append(Page(number=i, text="\n\n".join(lines)))
    return pages


def load_docx(path: Path) -> list[Page]:
    from docx import Document

    sections: list[list[str]] = [[]]
    for para in Document(str(path)).paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = (para.style.name if para.style is not None else "") or ""
        if style.startswith(("Heading", "Title")) and sections[-1]:
            sections.append([])
        sections[-1].append(text)
    return [Page(number=i, text="\n\n".join(s)) for i, s in enumerate(sections, start=1) if s]
