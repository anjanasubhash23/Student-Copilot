"use client";

import { useState } from "react";

// Topics mastered at the end of each active day: one series, so the title names it and there's no legend.
// Bars have 4px rounded tops anchored to the baseline, a 2px gap, recessive gridlines, a hover tooltip,
// and a table view for screen readers and anyone who prefers numbers.
type Point = { date: string; mastered: number };

const H = 180;
const PAD = { top: 12, right: 8, bottom: 22, left: 28 };

function topRounded(x: number, y: number, w: number, h: number, r: number): string {
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + rr} Q${x},${y} ${x + rr},${y} H${x + w - rr} Q${x + w},${y} ${x + w},${y + rr} V${y + h} Z`;
}

export function MasteredChart({ data, total }: { data: Point[]; total: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const points = data.slice(-30);
  const max = Math.max(1, total, ...points.map((p) => p.mastered));
  const width = 640;
  const plotW = width - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(points.length, 1);
  const barW = Math.max(2, Math.min(28, slot - 2));
  const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
  const ticks = [0, Math.round(max / 2), max];
  const short = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <figure className="space-y-2">
      <figcaption className="flex items-baseline justify-between">
        <span className="text-sm font-semibold">Topics mastered over time</span>
        <button className="text-xs text-accent hover:underline" onClick={() => setTable((t) => !t)}>
          {table ? "Show chart" : "Show table"}
        </button>
      </figcaption>
      {points.length === 0 ? (
        <p className="text-sm text-muted">Answer some questions to see your progress here.</p>
      ) : table ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted">
              <th className="font-normal">Day</th>
              <th className="text-right font-normal">Topics mastered</th>
            </tr>
          </thead>
          <tbody>
            {points.map((p) => (
              <tr key={p.date} className="border-t border-line">
                <td className="py-1">{short(p.date)}</td>
                <td className="py-1 text-right tabular-nums">{p.mastered}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${width} ${H}`} className="w-full" role="img" aria-label={`Topics mastered per day, latest ${points.at(-1)?.mastered} of ${total}`}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeWidth={1} />
                <text x={PAD.left - 6} y={y(t)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="var(--text-muted)">
                  {t}
                </text>
              </g>
            ))}
            {points.map((p, i) => {
              const x = PAD.left + i * slot + (slot - barW) / 2;
              const h = Math.max(0, y(0) - y(p.mastered));
              return (
                <g key={p.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  {/* hit target: the whole column, bigger than the bar */}
                  <rect x={PAD.left + i * slot} y={PAD.top} width={slot} height={plotH} fill="transparent" />
                  {h > 0 && <path d={topRounded(x, y(p.mastered), barW, h, 4)} fill="var(--bar)" opacity={hover === null || hover === i ? 1 : 0.55} />}
                </g>
              );
            })}
            {[0, points.length - 1].filter((v, i, a) => a.indexOf(v) === i).map((i) => (
              <text key={i} x={PAD.left + i * slot + slot / 2} y={H - 6} textAnchor="middle" fontSize={10} fill="var(--text-muted)">
                {short(points[i].date)}
              </text>
            ))}
          </svg>
          {hover !== null && (
            <div
              className="pointer-events-none absolute top-0 rounded-md border border-line bg-surface px-2 py-1 text-xs shadow-sm"
              style={{ left: `${((PAD.left + hover * slot + slot / 2) / width) * 100}%`, transform: "translateX(-50%)" }}
            >
              <div className="text-muted">{short(points[hover].date)}</div>
              <div className="tabular-nums">
                {points[hover].mastered} of {total} topics
              </div>
            </div>
          )}
        </div>
      )}
    </figure>
  );
}
