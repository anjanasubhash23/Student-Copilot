"""Turn a source (an uploaded file or a link) into located Pages. One loader per kind."""

from pathlib import Path

from core.ingest.schema import Page, SourceKind
from core.sources.detect import EXTENSIONS, UnsupportedFileError, detect_kind
from core.sources.fetch import FetchError
from core.sources.office import load_docx, load_pptx
from core.sources.pdf import ScannedPdfError, load_pdf
from core.sources.text import load_text
from core.sources.web import load_web
from core.sources.youtube import TranscriptError, is_youtube, is_youtube_playlist, load_youtube

# Errors whose message is written for the user, so it can be shown as the source's failure reason.
SourceError = (FetchError, ScannedPdfError, TranscriptError, UnsupportedFileError)


def load_file(kind: SourceKind, path: Path, ocr_lang: str = "eng") -> list[Page]:
    match kind:
        case "pdf":
            return load_pdf(path, ocr_lang)
        case "pptx":
            return load_pptx(path)
        case "docx":
            return load_docx(path)
        case "text":
            return load_text(path.read_text(encoding="utf-8"))
        case _:
            raise ValueError(f"{kind} is not a file kind")


__all__ = [
    "EXTENSIONS",
    "FetchError",
    "ScannedPdfError",
    "SourceError",
    "TranscriptError",
    "UnsupportedFileError",
    "detect_kind",
    "is_youtube",
    "is_youtube_playlist",
    "load_file",
    "load_pdf",
    "load_web",
    "load_youtube",
]
