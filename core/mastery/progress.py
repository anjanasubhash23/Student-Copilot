"""The progress view: topics mastered over time, rebuilt from the log of mastery changes."""

from datetime import date

from core.mastery.bkt import MASTERED
from core.storage.learning import MasteryEvent


def mastered_by_day(events: list[MasteryEvent]) -> list[dict[str, object]]:
    """For each day with activity, how many topics were mastered at the end of it. `events` oldest first."""
    current: dict[str, float] = {}
    days: dict[date, int] = {}
    for e in events:
        current[e.topic_id] = e.p_known
        days[e.ts.date()] = sum(p >= MASTERED for p in current.values())
    return [{"date": d.isoformat(), "mastered": n} for d, n in days.items()]
