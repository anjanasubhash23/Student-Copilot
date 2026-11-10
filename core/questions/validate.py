"""Keep a generated question only if it cites its excerpt, is well-formed, its numerical answer is reproduced
by running its solution, and a second LLM call agrees it is correct. Rejected questions are stored too
(status 'rejected', with the reasons), so validation quality can be audited."""

import math
from typing import Any

from core.llm import load_prompt, structured
from core.questions.excerpts import neutralize
from core.questions.numeric_runner import run_solution
from core.questions.schema import Question, QuestionDraft, ValidationOut


def structure_problems(d: QuestionDraft, n_excerpts: int) -> list[str]:
    problems = []
    if not 1 <= d.source <= n_excerpts:
        problems.append(f"cites excerpt {d.source}, which doesn't exist")
    if not d.stem.strip():
        problems.append("empty question")
    match d.type:
        case "mcq" | "msq":
            if not 3 <= len(d.options) <= 6:
                problems.append("needs 3 to 6 options")
            if len({o.strip().lower() for o in d.options}) != len(d.options):
                problems.append("duplicate options")
            if any(not 0 <= i < len(d.options) for i in d.correct):
                problems.append("correct index out of range")
            if len(set(d.correct)) != len(d.correct):
                problems.append("duplicate correct index")
            if d.type == "mcq" and len(d.correct) != 1:
                problems.append("mcq needs exactly one correct option")
            if d.type == "msq" and not d.correct:
                problems.append("msq needs at least one correct option")
        case "numeric":
            if d.numeric_answer is None or not math.isfinite(d.numeric_answer):
                problems.append("no numeric answer")
            if not d.solution_code:
                problems.append("no solution code")
        case "short":
            if not d.rubric.strip():
                problems.append("no rubric")
    return problems


def numeric_range(answer: float, tolerance: float | None) -> tuple[float, float]:
    """Accepted range. The model's tolerance is capped at 5% of the answer so a loose one can't accept anything."""
    default = max(abs(answer) * 0.01, 1e-6)
    cap = max(abs(answer) * 0.05, 1e-6)
    tol = min(abs(tolerance), cap) if tolerance else default
    return answer - tol, answer + tol


def render(d: QuestionDraft) -> str:
    lines = [f"Type: {d.type}", f"Question: {d.stem}"]
    lines += [f"  {i}. {o}{'  (marked correct)' if i in d.correct else ''}" for i, o in enumerate(d.options)]
    if d.type == "numeric":
        lines.append(f"Answer: {d.numeric_answer}")
    lines.append(f"Model answer: {d.answer}")
    if d.rubric:
        lines.append(f"Rubric: {d.rubric}")
    return "\n".join(lines)


def to_question(
    d: QuestionDraft,
    *,
    space_id: str,
    topic_id: str,
    topic_name: str,
    chunks: list[dict[str, Any]],
    extracted_by: str,
    timeout: float,
) -> Question:
    problems = structure_problems(d, len(chunks))
    validation: dict[str, Any] = {}
    low = high = None
    answer = d.answer
    if d.type in ("mcq", "msq") and not problems:
        answer = answer or "; ".join(d.options[i] for i in d.correct)

    if d.type == "numeric" and not problems:
        assert d.numeric_answer is not None and d.solution_code is not None
        low, high = numeric_range(d.numeric_answer, d.tolerance)
        run = run_solution(d.solution_code, timeout)
        validation["numeric"] = {"value": run.value, "error": run.error}
        if run.value is None:
            problems.append(f"solution didn't run: {run.error}")
        elif not low <= run.value <= high:
            problems.append(f"solution printed {run.value}, not {d.numeric_answer}")

    if not problems:
        excerpt = neutralize(chunks[d.source - 1]["text"], "excerpt")
        check = structured(
            load_prompt(
                "validate_question", topic=topic_name, excerpt=excerpt, question=neutralize(render(d), "question")
            ),
            ValidationOut,
        )
        validation["llm"] = check.model_dump()
        if not check.valid:
            problems.append(f"checker: {check.reason}")

    validation["problems"] = problems
    source = min(max(d.source, 1), len(chunks)) - 1
    return Question(
        id=Question.new_id(),
        space_id=space_id,
        topic_id=topic_id,
        type=d.type,
        stem=d.stem.strip(),
        options=[o.strip() for o in d.options] if d.type in ("mcq", "msq") else [],
        correct=sorted(set(d.correct)) if d.type in ("mcq", "msq") else [],
        answer=answer.strip(),
        num_low=low,
        num_high=high,
        rubric=d.rubric.strip(),
        explanation=d.explanation.strip(),
        solution_code=d.solution_code if d.type == "numeric" else None,
        chunk_id=chunks[source]["id"],
        validation=validation,
        status="rejected" if problems else "valid",
        extracted_by=extracted_by,
    )
