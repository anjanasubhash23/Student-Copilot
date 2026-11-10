from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.settings import get_settings
from core.ingest.schema import Chunk, Topic, TopicsOut
from core.llm import load_prompt, structured

Progress = Callable[[float], None]


def _topics_in(chunk: Chunk) -> list[Topic]:
    out = structured(load_prompt("topics", chunk=chunk.text), TopicsOut)
    return [
        Topic(name=t.name.strip(), summary=t.summary.strip(), chunks=[chunk.key], first_seen=chunk.id)
        for t in out.topics
        if t.name.strip()
    ]


def extract_topics(chunks: list[Chunk], on_progress: Progress | None = None) -> list[Topic]:
    """One LLM call per chunk; duplicates across chunks are resolved later in merge."""
    found: list[Topic] = []
    with ThreadPoolExecutor(get_settings().llm_concurrency) as pool:
        for done, topics in enumerate(pool.map(_topics_in, chunks), start=1):
            found.extend(topics)
            if on_progress:
                on_progress(done / len(chunks))
    return found
