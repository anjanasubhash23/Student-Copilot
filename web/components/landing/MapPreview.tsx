"use client";

import { useEffect, useState } from "react";

import { masteryVar } from "../mastery";

// A small illustrative topic map whose nodes fill in with mastery over time, like a learner progressing.
type N = { id: string; label: string; x: number; y: number };

const NODES: N[] = [
  { id: "bigo", label: "Big-O", x: 70, y: 70 },
  { id: "rec", label: "Recurrences", x: 210, y: 50 },
  { id: "master", label: "Master theorem", x: 350, y: 80 },
  { id: "dc", label: "Divide & conquer", x: 160, y: 170 },
  { id: "merge", label: "Merge sort", x: 320, y: 190 },
  { id: "greedy", label: "Greedy", x: 60, y: 260 },
  { id: "dp", label: "Dynamic programming", x: 230, y: 285 },
  { id: "knap", label: "0/1 Knapsack", x: 380, y: 300 },
];

// prerequisite → dependent
const EDGES: [string, string][] = [
  ["bigo", "rec"],
  ["rec", "master"],
  ["bigo", "dc"],
  ["rec", "dc"],
  ["dc", "merge"],
  ["master", "merge"],
  ["bigo", "greedy"],
  ["dc", "dp"],
  ["greedy", "dp"],
  ["dp", "knap"],
];

// Mastery per node at each step of the loop; null = not assessed yet.
const STEPS: (number | null)[][] = [
  [null, null, null, null, null, null, null, null],
  [0.55, 0.35, null, 0.3, null, 0.4, null, null],
  [0.8, 0.6, 0.35, 0.5, 0.3, 0.6, 0.2, null],
  [0.97, 0.85, 0.6, 0.75, 0.55, 0.8, 0.4, 0.2],
  [0.98, 0.97, 0.85, 0.96, 0.8, 0.97, 0.65, 0.45],
  [0.99, 0.98, 0.96, 0.98, 0.97, 0.98, 0.9, 0.7],
];

const pos = Object.fromEntries(NODES.map((n) => [n.id, n]));

export function MapPreview() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setStep(3);
      return;
    }
    const timer = setInterval(() => setStep((s) => (s + 1) % STEPS.length), 1600);
    return () => clearInterval(timer);
  }, []);

  const values = STEPS[step];
  const mastered = values.filter((v) => v !== null && v >= 0.95).length;

  return (
    <div className="float rounded-2xl border border-line bg-surface/80 p-4 shadow-2xl shadow-black/10 backdrop-blur">
      <div className="mb-2 flex items-center justify-between px-1 text-xs text-ink-2">
        <span className="font-medium text-ink">Algorithms · your map</span>
        <span className="tabular-nums">
          {mastered}/{NODES.length} mastered
        </span>
      </div>
      <svg viewBox="0 0 440 340" className="w-full" role="img" aria-label="Example topic map filling in with mastery">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--text-muted)" />
          </marker>
        </defs>
        {EDGES.map(([a, b]) => {
          const p = pos[a];
          const q = pos[b];
          const dx = q.x - p.x;
          const dy = q.y - p.y;
          const len = Math.hypot(dx, dy);
          const r = 13;
          return (
            <line
              key={`${a}-${b}`}
              x1={p.x + (dx / len) * r}
              y1={p.y + (dy / len) * r}
              x2={q.x - (dx / len) * (r + 3)}
              y2={q.y - (dy / len) * (r + 3)}
              stroke="var(--border)"
              strokeWidth={1.5}
              markerEnd="url(#arrow)"
            />
          );
        })}
        {NODES.map((n, i) => {
          const v = values[i];
          const fill = masteryVar(v ?? 0, v !== null);
          const done = v !== null && v >= 0.95;
          return (
            <g key={n.id}>
              {v !== null && !done && (
                <circle cx={n.x} cy={n.y} r={9} fill="none" stroke="var(--accent)" className="pulse-ring" />
              )}
              <circle cx={n.x} cy={n.y} r={13} fill="var(--surface)" />
              <circle cx={n.x} cy={n.y} r={11} fill={fill} style={{ transition: "fill 0.8s ease" }} />
              {done && (
                <text x={n.x} y={n.y + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill="var(--surface)">
                  ✓
                </text>
              )}
              <text x={n.x} y={n.y + 28} textAnchor="middle" fontSize={11} fill="var(--text-2)">
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
