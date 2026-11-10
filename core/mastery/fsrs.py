"""Spaced repetition for flashcards with FSRS (py-fsrs). A card's scheduling state is stored as JSON."""

import json
from datetime import datetime
from typing import Literal

from fsrs import Card, Rating, Scheduler

RatingName = Literal["again", "hard", "good", "easy"]
RATINGS: dict[RatingName, Rating] = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}

_scheduler = Scheduler()


def review(state: str | None, rating: RatingName, at: datetime) -> tuple[str, datetime]:
    """Apply a rating to a card's state (None for a new card). Returns the new state and when it is next due."""
    card = Card.from_dict(json.loads(state)) if state else Card()
    card, _log = _scheduler.review_card(card, RATINGS[rating], review_datetime=at)
    return json.dumps(card.to_dict()), card.due
