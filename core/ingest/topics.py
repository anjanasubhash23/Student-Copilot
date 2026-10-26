from concurrent.futures import ThreadPoolExecutor

from app.settings import get_settings
from core.ingest.schema import Chunk, Topic, TopicsOut
from core.llm import load_prompt, structured


def _topics_in(chunk: Chunk) -> list[Topic]:
    out = structured(load_prompt("topics", chunk=chunk.text), TopicsOut)
    pages = list(range(chunk.page_start, chunk.page_end + 1))
    return [Topic(name=t.name.strip(), summary=t.summary.strip(), pages=pages) for t in out.topics]


def extract_topics(chunks: list[Chunk]) -> list[Topic]:
    """One LLM call per chunk; duplicates across chunks are resolved later in merge."""
    with ThreadPoolExecutor(get_settings().llm_concurrency) as pool:
        return [t for found in pool.map(_topics_in, chunks) for t in found]
