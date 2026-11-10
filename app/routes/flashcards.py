"""Flashcards, reviewed with FSRS spaced repetition."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.deps import CurrentUser, Db, Map, Space
from core.mastery.fsrs import RatingName, review
from core.storage.clock import now
from core.storage.flashcards import SqliteFlashcardRepository
from core.storage.jobs import SqliteJobQueue
from core.storage.spaces import SqliteStudySpaceRepository

router = APIRouter(tags=["flashcards"])

NEW_CARDS_PER_SESSION = 10


@router.get("/spaces/{space_id}/flashcards/due")
def due_cards(space: Space, space_map: Map, user: CurrentUser, conn: Db) -> dict[str, Any]:
    """Cards due for review, then some new ones. Cards appear once their topic has been practised."""
    cards = SqliteFlashcardRepository(conn).due(user.id, space.id, now(), new_limit=NEW_CARDS_PER_SESSION)
    return {
        "cards": [
            {
                "id": c.flashcard.id,
                "front": c.flashcard.front,
                "back": c.flashcard.back,
                "topic_id": c.flashcard.topic_id,
                "topic": space_map.topics[c.flashcard.topic_id].name
                if c.flashcard.topic_id in space_map.topics
                else None,
                "new": c.due_at is None,
            }
            for c in cards
        ]
    }


class GenerateIn(BaseModel):
    topic_id: str


@router.post("/spaces/{space_id}/flashcards/generate", status_code=status.HTTP_202_ACCEPTED)
def generate_cards(body: GenerateIn, space: Space, space_map: Map, conn: Db) -> dict[str, bool]:
    if body.topic_id not in space_map.topics:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "topic not found")
    queued = SqliteJobQueue(conn).enqueue("flashcards", space.id, payload={"topic_id": body.topic_id}, dedupe=True)
    return {"queued": queued is not None}


class ReviewIn(BaseModel):
    rating: RatingName


class ReviewOut(BaseModel):
    due_at: datetime


@router.post("/flashcards/{card_id}/review")
def review_card(card_id: str, body: ReviewIn, user: CurrentUser, conn: Db) -> ReviewOut:
    repo = SqliteFlashcardRepository(conn)
    card = repo.get(card_id)
    space = SqliteStudySpaceRepository(conn).get(card.space_id) if card else None
    if card is None or space is None or space.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flashcard not found")
    at = now()
    state, due = review(repo.state(user.id, card.id), body.rating, at)
    repo.save_review(user.id, card, state, due, at)
    return ReviewOut(due_at=due)
