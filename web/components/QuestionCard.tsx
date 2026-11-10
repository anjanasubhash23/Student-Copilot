"use client";

import { useState } from "react";

import type { AnswerResponse, AnswerResult, Question } from "@/lib/api";

import { MathText } from "./MathText";
import { pct } from "./mastery";

type Props = {
  question: Question;
  onSubmit: (response: AnswerResponse) => Promise<AnswerResult>;
  onNext: () => void;
  nextLabel?: string;
};

export function QuestionCard({ question, onSubmit, onNext, nextLabel = "Next question" }: Props) {
  const [choice, setChoice] = useState<number | null>(null);
  const [choices, setChoices] = useState<number[]>([]);
  const [value, setValue] = useState("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready =
    (question.type === "mcq" && choice !== null) ||
    (question.type === "msq" && choices.length > 0) ||
    (question.type === "numeric" && value.trim() !== "" && Number.isFinite(Number(value))) ||
    (question.type === "short" && text.trim() !== "");

  async function submit() {
    const response: AnswerResponse =
      question.type === "mcq"
        ? { choice: choice ?? undefined }
        : question.type === "msq"
          ? { choices }
          : question.type === "numeric"
            ? { value: Number(value) }
            : { text };
    setBusy(true);
    setError(null);
    try {
      setResult(await onSubmit(response));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const answered = result !== null;
  const correctSet = new Set(result?.reveal.correct ?? []);

  return (
    <div className="card space-y-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">
        {{ mcq: "One answer", msq: "Select all that apply", numeric: "Numerical answer", short: "Short answer" }[question.type]}
      </div>
      <p className="text-base leading-relaxed">
        <MathText text={question.stem} />
      </p>

      {(question.type === "mcq" || question.type === "msq") && (
        <ul className="space-y-2">
          {question.options.map((opt, i) => {
            const picked = question.type === "mcq" ? choice === i : choices.includes(i);
            const tone = !answered
              ? picked
                ? "border-accent"
                : "border-line"
              : correctSet.has(i)
                ? "border-good"
                : picked
                  ? "border-critical"
                  : "border-line opacity-70";
            return (
              <li key={i}>
                <label className={`flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2 ${tone}`}>
                  <input
                    type={question.type === "mcq" ? "radio" : "checkbox"}
                    name={question.id}
                    className="mt-1"
                    disabled={answered}
                    checked={picked}
                    onChange={() =>
                      question.type === "mcq"
                        ? setChoice(i)
                        : setChoices((c) => (c.includes(i) ? c.filter((x) => x !== i) : [...c, i]))
                    }
                  />
                  <MathText text={opt} />
                  {answered && correctSet.has(i) && <span className="ml-auto text-sm text-good">✓ correct</span>}
                </label>
              </li>
            );
          })}
        </ul>
      )}
      {question.type === "numeric" && (
        <input
          className="input max-w-xs"
          inputMode="decimal"
          placeholder="Your answer"
          value={value}
          disabled={answered}
          onChange={(e) => setValue(e.target.value)}
        />
      )}
      {question.type === "short" && (
        <textarea
          className="input min-h-28"
          placeholder="Answer in a few sentences"
          value={text}
          disabled={answered}
          onChange={(e) => setText(e.target.value)}
        />
      )}

      {error && <p className="text-sm text-critical">{error}</p>}

      {!answered ? (
        <button className="btn" disabled={!ready || busy} onClick={submit}>
          {busy ? (question.type === "short" ? "Marking…" : "Checking…") : "Submit"}
        </button>
      ) : (
        <div className="space-y-3 border-t border-line pt-4">
          <p className={`font-medium ${result.mark.correct ? "text-good" : "text-critical"}`}>
            {result.mark.correct ? "✓ Correct" : "✗ Not quite"}
            {question.type !== "mcq" && result.mark.score > 0 && result.mark.score < 1 && ` · ${pct(result.mark.score)}`}
          </p>
          {result.mark.feedback && <p className="text-sm text-ink-2">{result.mark.feedback}</p>}
          {(question.type === "numeric" || question.type === "short") && result.reveal.answer && (
            <p className="text-sm">
              <span className="text-muted">Answer: </span>
              <MathText text={result.reveal.answer} />
            </p>
          )}
          {result.reveal.explanation && (
            <p className="text-sm text-ink-2">
              <MathText text={result.reveal.explanation} />
            </p>
          )}
          {result.source && (
            <p className="text-xs text-muted">
              From {result.source.name}
              {result.source.location && `, ${result.source.location}`}
            </p>
          )}
          <p className="text-sm">
            <span className="text-muted">{result.mastery.name}: </span>
            {pct(result.mastery.p_known)} likely known{result.mastery.mastered && " ✓ mastered"}
          </p>
          {result.also_updated.length > 0 && (
            <p className="text-xs text-muted">
              Also updated: {result.also_updated.slice(0, 4).map((t) => `${t.name} ${pct(t.p_known)}`).join(", ")}
              {result.also_updated.length > 4 && ` and ${result.also_updated.length - 4} more`}
            </p>
          )}
          <button className="btn" onClick={onNext}>
            {nextLabel}
          </button>
        </div>
      )}
    </div>
  );
}
