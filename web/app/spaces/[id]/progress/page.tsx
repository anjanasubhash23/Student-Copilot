"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { MasteredChart } from "@/components/MasteredChart";
import { pct } from "@/components/mastery";
import { api, errorMessage, type Progress } from "@/lib/api";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-sm text-ink-2">{label}</div>
    </div>
  );
}

export default function ProgressPage() {
  const { id } = useParams<{ id: string }>();
  const [p, setP] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.progress(id).then(setP).catch((e) => setError(errorMessage(e)));
  }, [id]);

  if (error) return <p className="text-sm text-critical">{error}</p>;
  if (!p) return <p className="text-sm text-muted">Loading…</p>;

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label={`of ${p.topics} topics mastered`} value={String(p.mastered)} />
        <Stat label="topics assessed" value={String(p.assessed)} />
        <Stat label={`right, last ${p.attempts} answers`} value={p.recent_accuracy === null ? "–" : pct(p.recent_accuracy)} />
        <Stat label="cards reviewed today" value={String(p.reviewed_today)} />
      </div>
      <div className="card">
        <MasteredChart data={p.mastered_over_time} total={p.topics} />
      </div>
      <div className="grid gap-6 md:grid-cols-2">
        <div className="card space-y-2">
          <h2 className="text-sm font-semibold">Weakest topics</h2>
          {p.weakest.length === 0 ? (
            <p className="text-sm text-muted">Everything is mastered.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {p.weakest.map((t) => (
                <li key={t.id} className="flex justify-between gap-2">
                  <Link href={`/spaces/${id}/practice?topic=${encodeURIComponent(t.id)}`} className="text-accent hover:underline">
                    {t.name}
                  </Link>
                  <span className="tabular-nums text-ink-2">{pct(t.p_known)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="card space-y-2">
          <h2 className="text-sm font-semibold">Due for review</h2>
          {p.due_for_review.length === 0 ? (
            <p className="text-sm text-muted">Nothing due.</p>
          ) : (
            <>
              <ul className="space-y-1 text-sm">
                {p.due_for_review.map((t) => (
                  <li key={t.id} className="flex justify-between gap-2">
                    <span>{t.name}</span>
                    <span className="tabular-nums text-ink-2">{t.cards} cards</span>
                  </li>
                ))}
              </ul>
              <Link href={`/spaces/${id}/flashcards`} className="btn-ghost">
                Review now
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
