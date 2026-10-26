from core.ingest.chunk import chunk_pages
from core.ingest.schema import Page


def test_chunks_track_pages_and_overlap():
    pages = [Page(number=1, text="a" * 40 + "\n\n" + "b" * 20), Page(number=2, text="c" * 40)]
    chunks = chunk_pages(pages, max_chars=70, overlap=25)
    assert [(c.page_start, c.page_end) for c in chunks] == [(1, 1), (1, 2)]
    assert chunks[1].text == "b" * 20 + "\n\n" + "c" * 40  # "b" paragraph carried over


def test_splits_paragraphs_longer_than_max():
    chunks = chunk_pages([Page(number=1, text=" ".join(["word"] * 100))], max_chars=50, overlap=0)
    assert len(chunks) > 1
    assert all(len(c.text) <= 50 for c in chunks)


def test_empty_pages_give_no_chunks():
    assert chunk_pages([Page(number=1, text=""), Page(number=2, text="  ")]) == []
