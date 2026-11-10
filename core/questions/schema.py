from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from core.storage.clock import now

QuestionType = Literal["mcq", "msq", "short", "numeric"]
QuestionStatus = Literal["valid", "rejected"]


class Question(BaseModel):
    id: str
    space_id: str
    topic_id: str
    type: QuestionType
    stem: str
    options: list[str] = Field(default_factory=list)  # mcq / msq
    correct: list[int] = Field(default_factory=list)  # indexes into options (mcq: exactly one)
    answer: str = ""  # model answer as text, shown after answering
    num_low: float | None = None  # numeric: accepted range
    num_high: float | None = None
    rubric: str = ""  # short answer: what a full-marks answer must contain
    explanation: str = ""
    solution_code: str | None = None  # numeric: Python that prints the answer
    chunk_id: str  # the chunk the question is based on (its citation)
    validation: dict[str, Any] = Field(default_factory=dict)
    status: QuestionStatus = "valid"
    extracted_by: str
    created_at: datetime = Field(default_factory=now)

    @staticmethod
    def new_id() -> str:
        return uuid4().hex

    def public(self) -> dict[str, Any]:
        """What the learner sees before answering: no answers, rubric or solution."""
        return {"id": self.id, "topic_id": self.topic_id, "type": self.type, "stem": self.stem, "options": self.options}


class Response(BaseModel):
    """A learner's answer. Which field is used depends on the question type."""

    choice: int | None = None  # mcq
    choices: list[int] | None = None  # msq
    value: float | None = None  # numeric
    text: str | None = Field(default=None, max_length=5000)  # short


class Mark(BaseModel):
    correct: bool
    score: float = Field(ge=0, le=1)
    feedback: str = ""


# LLM output shapes


class QuestionDraft(BaseModel):
    type: QuestionType
    stem: str = Field(description="The question. Use $...$ for maths.")
    options: list[str] = Field(default_factory=list, description="mcq/msq: 4 options. Empty for short/numeric.")
    correct: list[int] = Field(
        default_factory=list, description="mcq: [index of the one right option]; msq: indexes of all right options."
    )
    answer: str = Field(description="The correct answer written out, as a teacher would.")
    rubric: str = Field(default="", description="short: the points a full-marks answer must make.")
    numeric_answer: float | None = Field(default=None, description="numeric: the exact answer.")
    tolerance: float | None = Field(default=None, description="numeric: accepted absolute error.")
    solution_code: str | None = Field(
        default=None, description="numeric: Python using only the standard library that prints the answer."
    )
    explanation: str = Field(description="Why the answer is right, in 1-3 sentences.")
    source: int = Field(description="Number of the excerpt the question is based on.")


class QuestionsOut(BaseModel):
    questions: list[QuestionDraft]


class ValidationOut(BaseModel):
    valid: bool = Field(description="True only if the question is clear and the given answer is correct.")
    reason: str = Field(description="One sentence.")


class GradeOut(BaseModel):
    score: float = Field(description="0 to 1: how much of the rubric the answer meets.")
    feedback: str = Field(description="One or two sentences to the student.")


class FlashcardDraft(BaseModel):
    front: str = Field(description="A question or term. Use $...$ for maths.")
    back: str = Field(description="The answer, short.")
    source: int = Field(description="Number of the excerpt the card is based on.")


class FlashcardsOut(BaseModel):
    cards: list[FlashcardDraft]
