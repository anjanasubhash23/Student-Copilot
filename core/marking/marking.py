import math

from core.llm import load_prompt, structured
from core.questions.schema import GradeOut, Mark, Question, Response

SHORT_PASS = 0.6  # a short answer scoring this much of the rubric counts as correct for mastery


class InvalidResponseError(ValueError):
    pass


def mark(question: Question, response: Response) -> Mark:
    match question.type:
        case "mcq":
            if response.choice is None:
                raise InvalidResponseError("choose an option")
            ok = [response.choice] == question.correct
            return Mark(correct=ok, score=float(ok))
        case "msq":
            if response.choices is None:
                raise InvalidResponseError("choose the options that apply")
            return mark_msq(set(response.choices), set(question.correct), len(question.options))
        case "numeric":
            if response.value is None or not math.isfinite(response.value):
                raise InvalidResponseError("enter a number")
            assert question.num_low is not None and question.num_high is not None
            ok = question.num_low <= response.value <= question.num_high
            return Mark(correct=ok, score=float(ok))
        case "short":
            if not response.text or not response.text.strip():
                raise InvalidResponseError("write an answer")
            return mark_short(question, response.text)


def mark_msq(chosen: set[int], correct: set[int], n_options: int) -> Mark:
    """Correct only if exactly right; partial score = (right picks - wrong picks) / number right, at least 0."""
    if any(c < 0 or c >= n_options for c in chosen):
        raise InvalidResponseError("unknown option")
    score = max(0.0, (len(chosen & correct) - len(chosen - correct)) / len(correct))
    return Mark(correct=chosen == correct, score=score)


def mark_short(question: Question, text: str) -> Mark:
    prompt = load_prompt(
        "grade", question=question.stem, answer=question.answer, rubric=question.rubric, response=text.strip()
    )
    out = structured(prompt, GradeOut)
    score = min(max(out.score, 0.0), 1.0)
    return Mark(correct=score >= SHORT_PASS, score=score, feedback=out.feedback)
