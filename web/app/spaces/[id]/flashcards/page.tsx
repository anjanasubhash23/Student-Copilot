"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { MathText } from "@/components/MathText";
import { api, errorMessage, type Card } from "@/lib/api";

const RATINGS = [
  ["again", "Again", "forgot"],
  ["hard", "Hard", "barely"],
  ["good", "Good", "recalled"],
  ["easy", "Easy", "instantly"],
] as const;

export default function FlashcardsPage() {
  const { id } = useParams<{ id: string }>();
  const [cards, setCards] = useState<Card[] | null>(null);
  const [index, setIndex] = useState(0);
  const [shown, setShown] = useState(false);
  const [done, setDone] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setIndex(0);
    setShown(false);
    api
      .dueCards(id)
      .then((r) => setCards(r.cards))
      .catch((e) => setError(errorMessage(e)));
  }, [id]);

  useEffect(load, [load]);

  if (error) return <p className="text-sm text-critical">{error}</p>;
  if (!cards) return <p className="text-sm text-muted">Loading…</p>;

  const card = cards[index];
  if (!card)
    return (
      <div className="card max-w-xl space-y-3">
        <p>{done > 0 ? `Done: ${done} cards reviewed.` : "No cards due."}</p>
        <p className="text-sm text-ink-2">
          Cards are made for each topic the first time you practise it, then come back just before you&apos;d forget them.
        </p>
        <button className="btn-ghost" onClick={load}>
          Check again
        </button>
      </div>
    );

  async function rate(rating: (typeof RATINGS)[number][0]) {
    try {
      await api.review(card.id, rating);
      setDone((d) => d + 1);
      setShown(false);
      setIndex((i) => i + 1);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <div className="max-w-xl space-y-3">
      <p className="text-sm text-ink-2">
        Card {index + 1} of {cards.length}
        {card.topic && ` · ${card.topic}`}
        {card.new && " · new"}
      </p>
      <div className="card min-h-48 space-y-4">
        <p className="text-lg">
          <MathText text={card.front} />
        </p>
        {shown && (
          <p className="border-t border-line pt-4 text-ink-2">
            <MathText text={card.back} />
          </p>
        )}
      </div>
      {!shown ? (
        <button className="btn" onClick={() => setShown(true)}>
          Show answer
        </button>
      ) : (
        <div className="grid grid-cols-4 gap-2">
          {RATINGS.map(([value, label, hint]) => (
            <button key={value} className="btn-ghost flex-col gap-0" onClick={() => rate(value)}>
              <span>{label}</span>
              <span className="text-xs font-normal text-muted">{hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
