from core.ingest.clean import clean_pages
from core.ingest.schema import Page


def _page(n: int, body: str) -> Page:
    return Page(number=n, text=f"CS301 Database Systems\n{body}\nLecture {n}\n{n}")


def test_strips_repeated_headers_footers_and_page_numbers():
    bodies = ["Keys identify rows.", "Joins combine tables.", "Indexes speed lookups.", "Locks isolate writers."]
    pages = clean_pages([_page(i, body) for i, body in enumerate(bodies, start=1)])
    assert [p.text for p in pages] == bodies


def test_rejoins_hyphenated_words():
    [page] = clean_pages([Page(number=1, text="normal-\nization is   key")])
    assert page.text == "normalization is key"


def test_keeps_short_documents_untouched_apart_from_whitespace():
    [page] = clean_pages([Page(number=1, text="Title\n\n\n\nBody")])
    assert page.text == "Title\n\nBody"
