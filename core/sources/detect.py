"""Work out an upload's kind from its content, never from its file name or the browser's content type."""

import io
import zipfile

from core.ingest.schema import SourceKind

TEXT_EXTENSIONS = (".md", ".markdown", ".txt")


class UnsupportedFileError(Exception):
    pass


def detect_kind(data: bytes, filename: str) -> SourceKind:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
        except zipfile.BadZipFile as exc:
            raise UnsupportedFileError("the file looks like a damaged Office document") from exc
        if "ppt/presentation.xml" in names:
            return "pptx"
        if "word/document.xml" in names:
            return "docx"
        raise UnsupportedFileError("only .pptx and .docx Office files are supported")
    # Text is accepted only with a text extension, so a renamed binary isn't fed to the LLM as "text".
    if filename.lower().endswith(TEXT_EXTENSIONS) and b"\x00" not in data:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileError("text files must be UTF-8") from exc
        return "text"
    raise UnsupportedFileError("supported files: PDF, PPTX, DOCX, Markdown, TXT")


EXTENSIONS: dict[SourceKind, str] = {"pdf": ".pdf", "pptx": ".pptx", "docx": ".docx", "text": ".txt"}
