"""Web page or linked PDF → Pages. The fetch is SSRF-protected (core.sources.fetch)."""

import trafilatura

from core.ingest.schema import Page
from core.sources.fetch import FetchError, fetch
from core.sources.pdf import load_pdf
from core.sources.text import load_text


def load_web(url: str, max_bytes: int) -> tuple[list[Page], str]:
    """Returns the pages and a display name (the page title, or the URL)."""
    fetched = fetch(url, max_bytes)
    if fetched.content_type == "application/pdf":
        return load_pdf(fetched.body), fetched.url
    if fetched.content_type == "text/plain":
        return load_text(fetched.body.decode("utf-8", errors="replace")), fetched.url
    html = fetched.body.decode("utf-8", errors="replace")
    # Markdown output keeps headings, so the page splits into sections like a .md file.
    text = trafilatura.extract(html, url=fetched.url, output_format="markdown", include_comments=False)
    if not text or not text.strip():
        raise FetchError("couldn't find the main text of that page")
    meta = trafilatura.extract_metadata(html, default_url=fetched.url)
    title = meta.title if meta and meta.title else fetched.url
    return load_text(text), title
