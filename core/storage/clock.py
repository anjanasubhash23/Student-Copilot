from datetime import UTC, datetime


def now() -> datetime:
    return datetime.now(UTC)


def iso(when: datetime) -> str:
    """Fixed-width UTC timestamps, so SQLite can compare them as strings."""
    return when.astimezone(UTC).isoformat(timespec="microseconds")
