"use client";

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { MathText } from "@/components/MathText";
import { api, errorMessage, type Explanation } from "@/lib/api";

type Turn = { question: string; reply?: Explanation; error?: string };

// Renders the answer paragraph by paragraph; [n] markers stay as text and match the numbered sources below.
function Answer({ reply }: { reply: Explanation }) {
  return (
    <div className="space-y-3">
      {reply.covered_prerequisites.length > 0 && (
        <p className="text-xs text-muted">Starts with what this builds on: {reply.covered_prerequisites.join(", ")}</p>
      )}
      {reply.answer.split(/\n{2,}/).map((para, i) => (
        <p key={i} className="whitespace-pre-wrap leading-relaxed">
          <MathText text={para} />
        </p>
      ))}
      {reply.citations.length > 0 && (
        <ol className="space-y-0.5 border-t border-line pt-2 text-xs text-ink-2">
          {reply.citations.map((c) => (
            <li key={c.n}>
              [{c.n}] {c.source}
              {c.location && `, ${c.location}`}
              {c.topic && <span className="text-muted"> · {c.topic}</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Chat() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState(params.get("q") ?? "");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [turns]);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    const question = draft.trim();
    if (!question) return;
    setDraft("");
    setBusy(true);
    setTurns((t) => [...t, { question }]);
    try {
      const reply = await api.explain(id, question);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, reply } : turn)));
    } catch (err) {
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: errorMessage(err) } : turn)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      {turns.length === 0 && (
        <p className="text-sm text-ink-2">
          Ask anything about your material. Answers come only from your sources, with citations, and start with any
          prerequisite you haven&apos;t mastered yet.
        </p>
      )}
      {turns.map((t, i) => (
        <div key={i} className="space-y-2">
          <div className="ml-auto w-fit max-w-[85%] rounded-lg bg-surface-2 px-4 py-2 text-sm">{t.question}</div>
          <div className="card text-sm">
            {t.reply ? <Answer reply={t.reply} /> : t.error ? <p className="text-critical">{t.error}</p> : <p className="text-muted">Thinking…</p>}
          </div>
        </div>
      ))}
      <div ref={end} />
      <form onSubmit={ask} className="sticky bottom-4 flex gap-2 rounded-lg bg-surface py-2">
        <input className="input" placeholder="e.g. Why does 3NF need 2NF first?" value={draft} maxLength={2000} onChange={(e) => setDraft(e.target.value)} />
        <button className="btn shrink-0" disabled={busy || !draft.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}

export default function ExplainPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <Chat />
    </Suspense>
  );
}
