"""PDF → one Page per page. Pages with (almost) no text layer are scanned images and go through OCR."""

import io
import logging
import shutil
from pathlib import Path

import pymupdf

from core.ingest.schema import Page

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 25  # less than this on a page means there's no usable text layer
OCR_DPI = 200


class ScannedPdfError(Exception):
    pass


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def _ocr(page: pymupdf.Page, lang: str) -> str:
    import pytesseract
    from PIL import Image

    png = page.get_pixmap(dpi=OCR_DPI).tobytes("png")
    text: str = pytesseract.image_to_string(Image.open(io.BytesIO(png)), lang=lang)
    return text


def load_pdf(source: Path | bytes, ocr_lang: str = "eng") -> list[Page]:
    doc = pymupdf.open(stream=source, filetype="pdf") if isinstance(source, bytes) else pymupdf.open(source)
    with doc:
        pages = []
        scanned = 0
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text()
            if len(text.strip()) < MIN_TEXT_CHARS and page.get_images():
                scanned += 1
                if ocr_available():
                    text = _ocr(page, ocr_lang)
            pages.append(Page(number=i + 1, text=text))
    if scanned and not ocr_available():
        if scanned == len(pages):
            raise ScannedPdfError("this PDF is scanned images; install Tesseract (brew install tesseract) to read it")
        log.warning("%d scanned pages skipped: Tesseract is not installed", scanned)
    return pages
