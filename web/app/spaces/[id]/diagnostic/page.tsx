"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { QuestionCard } from "@/components/QuestionCard";
import { api, errorMessage, type DiagnosticStep } from "@/lib/api";

export default function DiagnosticPage() {
  const { id } = useParams<{ id: string }>();
  const [step, setStep] = useState<DiagnosticStep | null>(null);
  const [pending, setPending] = useState<DiagnosticStep | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      setStep(await api.startDiagnostic(id));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (!step)
    return (
      <div className="card max-w-xl space-y-3">
        <h2 className="font-semibold">Diagnostic</h2>
        <p className="text-sm text-ink-2">
          A few questions picked from across the map. Each answer also tells us about related topics: get an advanced
          topic right and its prerequisites go up too. So a short quiz colours the whole map.
        </p>
        <p className="text-xs text-muted">The first question may take a minute while questions are written from your material.</p>
        {error && <p className="text-sm text-critical">{error}</p>}
        <button className="btn" disabled={busy} onClick={start}>
          {busy ? "Preparing…" : "Start"}
        </button>
      </div>
    );

  if (step.done)
    return (
      <div className="card max-w-xl space-y-3">
        <h2 className="font-semibold">Diagnostic complete</h2>
        <p className="text-sm text-ink-2">Your map is now coloured by what you probably know.</p>
        <div className="flex gap-2">
          <Link href={`/spaces/${id}`} className="btn">
            See your map
          </Link>
          <Link href={`/spaces/${id}/practice`} className="btn-ghost">
            Practise weak topics
          </Link>
        </div>
      </div>
    );

  return (
    <div className="max-w-2xl space-y-3">
      <p className="text-sm text-ink-2">
        Question {step.number} of {step.total}
      </p>
      {error && <p className="text-sm text-critical">{error}</p>}
      {step.question && (
        <QuestionCard
          key={step.question.id}
          question={step.question}
          nextLabel={busy ? "Preparing…" : pending?.done ? "Finish" : "Next question"}
          onSubmit={async (response) => {
            setBusy(true);
            try {
              // The answer returns the next question too; hold it until the learner has read the feedback.
              const r = await api.answerDiagnostic(id, step.diagnostic_id, step.question!.id, response);
              setPending(r.next);
              return r.result;
            } finally {
              setBusy(false);
            }
          }}
          onNext={() => {
            if (pending) setStep(pending);
            setPending(null);
          }}
        />
      )}
    </div>
  );
}
