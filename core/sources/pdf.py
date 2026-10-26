from pathlib import Path

from pypdf import PdfReader

from core.ingest.schema import Page


def load_pdf(path: Path) -> list[Page]:
    reader = PdfReader(path)
    return [Page(number=i, text=page.extract_text() or "") for i, page in enumerate(reader.pages, start=1)]
