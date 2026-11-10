"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { MasteryMap } from "@/components/MasteryMap";
import { pct } from "@/components/mastery";
import { api, ApiError, errorMessage, type MapTopic, type SpaceGraph } from "@/lib/api";

export default function MapPage() {
  const { id } = useParams<{ id: string }>();
  const [graph, setGraph] = useState<SpaceGraph | null>(null);
  const [selected, setSelected] = useState<MapTopic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cardsNote, setCardsNote] = useState<string | null>(null);

  useEffect(() => {
    api
      .graph(id)
      .then(setGraph)
      .catch((e) => setError(e instanceof ApiError && e.status === 503 ? e.message : errorMessage(e)));
  }, [id]);

  if (error) return <p className="text-sm text-critical">{error}</p>;
  if (!graph) return <p className="text-sm text-muted">Loading the map…</p>;
  if (graph.topics.length === 0)
    return (
      <div className="card max-w-xl space-y-3">
        <p>No topics yet.</p>
        <p className="text-sm text-ink-2">Add your notes, slides, links or videos; the map appears once they&apos;re read.</p>
        <Link href={`/spaces/${id}/sources`} className="btn">
          Add sources
        </Link>
      </div>
    );

  const names = new Map(graph.topics.map((t) => [t.id, t.name]));
  const assessed = graph.topics.filter((t) => t.assessed).length;
  const mastered = graph.topics.filter((t) => t.mastered).length;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-3">
        <p className="text-sm text-ink-2">
          {graph.topics.length} topics in {graph.units.length} units · {mastered} mastered · {assessed} assessed
          {assessed === 0 && (
            <>
              {" · "}
              <Link href={`/spaces/${id}/diagnostic`} className="text-accent hover:underline">
                take the diagnostic
              </Link>{" "}
              to colour the map
            </>
          )}
        </p>
        <MasteryMap graph={graph} onSelect={(t) => { setSelected(t); setCardsNote(null); }} />
      </div>
      <aside className="space-y-4">
        {selected ? (
          <div className="card space-y-3">
            <h2 className="font-semibold">{selected.name}</h2>
            <p className="text-sm text-ink-2">{selected.summary}</p>
            <p className="text-sm">
              {selected.assessed ? `${pct(selected.p_known)} likely known` : "Not assessed yet"}
              {selected.mastered && " · ✓ mastered"}
            </p>
            {selected.prerequisites.length > 0 && (
              <p className="text-sm text-ink-2">
                <span className="text-muted">Builds on: </span>
                {selected.prerequisites.map((p) => names.get(p) ?? p).join(", ")}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <Link className="btn" href={`/spaces/${id}/practice?topic=${encodeURIComponent(selected.id)}`}>
                Practise
              </Link>
              <Link className="btn-ghost" href={`/spaces/${id}/explain?q=${encodeURIComponent(`Explain ${selected.name}`)}`}>
                Explain
              </Link>
              <button
                className="btn-ghost"
                onClick={async () => {
                  const r = await api.makeCards(id, selected.id).catch((e) => setCardsNote(errorMessage(e)));
                  if (r) setCardsNote("Making flashcards; they'll be in the Flashcards tab shortly.");
                }}
              >
                Make flashcards
              </button>
            </div>
            {cardsNote && <p className="text-xs text-muted">{cardsNote}</p>}
          </div>
        ) : (
          <p className="text-sm text-muted">Click a topic to study it.</p>
        )}
        <div className="card">
          <h2 className="mb-2 text-sm font-semibold">Units</h2>
          <ol className="space-y-1 text-sm">
            {graph.units.map((u) => (
              <li key={u.id} className="text-ink-2">
                {u.order}. {u.name}
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </div>
  );
}
