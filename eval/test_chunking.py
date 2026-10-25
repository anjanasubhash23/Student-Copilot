from core.ingest.pdf import chunk_pages


def test_chunks_respect_size_and_pages():
    pages = ["intro para\n\n" + "a" * 50, "b" * 50 + "\n\nlast"]
    chunks = chunk_pages(pages, max_chars=70)
    assert all(len(c.text) <= 70 for c in chunks)
    assert chunks[0].page == 1
    assert chunks[-1].page == 2
    assert "a" * 50 in chunks[0].text


def test_empty_pages_give_no_chunks():
    assert chunk_pages(["", "  \n\n "]) == []
