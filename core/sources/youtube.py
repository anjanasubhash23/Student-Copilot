"""YouTube video → Pages of about a minute of transcript each, so citations can point to a timestamp."""

import re

from core.ingest.schema import Page

VIDEO_ID = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)"
    r"(?P<id>[A-Za-z0-9_-]{11})(?:[?&#/].*)?$"
)
WINDOW_SECONDS = 60.0


class TranscriptError(Exception):
    pass


def video_id(url: str) -> str | None:
    match = VIDEO_ID.match(url.strip())
    return match.group("id") if match else None


def is_youtube(url: str) -> bool:
    return video_id(url) is not None


def group_snippets(snippets: list[tuple[float, str]], window: float = WINDOW_SECONDS) -> list[Page]:
    """(start seconds, text) pieces → one Page per `window` seconds, stamped with where it starts."""
    pages: list[Page] = []
    texts: list[str] = []
    start = 0.0
    for at, text in snippets:
        if texts and at - start >= window:
            pages.append(Page(number=len(pages) + 1, text=" ".join(texts), timestamp=start))
            texts = []
        if not texts:
            start = at
        cleaned = " ".join(text.split())
        if cleaned:
            texts.append(cleaned)
    if texts:
        pages.append(Page(number=len(pages) + 1, text=" ".join(texts), timestamp=start))
    return pages


def load_youtube(url: str, languages: tuple[str, ...] = ("en", "en-US", "en-GB")) -> list[Page]:
    from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi

    vid = video_id(url)
    if vid is None:
        raise TranscriptError("not a YouTube video link")
    try:
        transcript = YouTubeTranscriptApi().fetch(vid, languages=languages)
    except CouldNotRetrieveTranscript as exc:
        raise TranscriptError(f"this video has no transcript we can read ({type(exc).__name__})") from exc
    return group_snippets([(s.start, s.text) for s in transcript.snippets])
