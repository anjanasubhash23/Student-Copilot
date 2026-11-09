from core.ingest.recall import parse_labels, score_topics
from core.ingest.schema import Topic


def test_parse_labels_handles_alternatives_and_comments() -> None:
    text = "# DBMS syllabus\nThird Normal Form | 3NF\n\nB+ Tree  # indexing\n"
    assert parse_labels(text) == [["Third Normal Form", "3NF"], ["B+ Tree"]]


def test_score_topics() -> None:
    labels = parse_labels("Third Normal Form | 3NF\nB+ Tree\nTwo-Phase Locking\nHashing")
    topics = [
        Topic(name="3NF", summary=""),  # matched via the label's alternative
        Topic(name="B+ Trees", summary=""),  # plural still matches
        Topic(name="Hash Index", summary="", aliases=["Hashing"]),  # matched via the topic's alias
        Topic(name="Course Logistics", summary=""),
    ]
    score = score_topics(labels, topics)
    assert score.missed == ["Two-Phase Locking"]
    assert score.extra == ["Course Logistics"]
    assert score.recall == 0.75
    assert score.precision == 0.75


def test_score_topics_empty() -> None:
    score = score_topics([], [])
    assert (score.recall, score.precision) == (0.0, 0.0)
