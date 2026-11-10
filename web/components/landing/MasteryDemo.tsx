"use client";

import { useEffect, useRef, useState } from "react";

// One answer moving a mastery bar: animates the first time it scrolls into view.
export function MasteryDemo() {
  const ref = useRef<HTMLDivElement>(null);
  const [answered, setAnswered] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setTimeout(() => setAnswered(true), 700);
          observer.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const before = 42;
  const after = 71;
  const value = answered ? after : before;

  return (
    <div ref={ref} className="rounded-2xl border border-line bg-surface p-6 shadow-xl shadow-black/5">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">Practice · Master theorem</div>
      <p className="mt-3 text-base">
        What is the running time of <span className="font-mono">T(n) = 2T(n/2) + n</span>?
      </p>
      <div className="mt-4 space-y-2">
        {["Θ(n)", "Θ(n log n)", "Θ(n²)"].map((opt) => {
          const right = opt === "Θ(n log n)";
          return (
            <div
              key={opt}
              className={`rounded-md border px-3 py-2 text-sm transition-colors duration-500 ${
                answered && right ? "border-good" : "border-line"
              }`}
            >
              {opt}
              {answered && right && <span className="float-right text-good">✓ correct</span>}
            </div>
          );
        })}
      </div>
      <div className="mt-6">
        <div className="flex justify-between text-sm">
          <span className="text-ink-2">Master theorem</span>
          <span className="tabular-nums font-medium">{value}% likely known</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-2">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-1000 ease-out"
            style={{ width: `${value}%` }}
          />
        </div>
        <p className={`mt-3 text-xs text-muted transition-opacity duration-700 ${answered ? "opacity-100" : "opacity-0"}`}>
          Also updated: Recurrences 64% → 78%, Big-O 81% → 88%
        </p>
      </div>
    </div>
  );
}
