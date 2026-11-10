"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

import type { MapTopic, SpaceGraph } from "@/lib/api";

import { LEGEND, MASTERED, masteryVar, pct } from "./mastery";

// The force-graph library touches `window`, so it only loads in the browser.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

type Node = MapTopic & { x?: number; y?: number };
type Link = { source: string | Node; target: string | Node; confidence: number };

// Canvas can't read CSS variables, so resolve them (and re-resolve when the colour scheme changes).
function useCssColors(): (v: string) => string {
  const [scheme, setScheme] = useState(0);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const bump = () => setScheme((s) => s + 1);
    mq.addEventListener("change", bump);
    return () => mq.removeEventListener("change", bump);
  }, []);
  return useMemo(() => {
    const style = typeof window === "undefined" ? null : getComputedStyle(document.documentElement);
    return (v: string) => {
      const name = v.match(/var\((--[\w-]+)\)/)?.[1];
      return name && style ? style.getPropertyValue(name).trim() || "#888" : v;
    };
  }, [scheme]);
}

export function MasteryMap({ graph, onSelect }: { graph: SpaceGraph; onSelect: (t: MapTopic) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 600, height: 520 });
  const [hover, setHover] = useState<Node | null>(null);
  const color = useCssColors();

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: 520 }));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  // Fresh objects each time the graph changes: the library mutates nodes (adds x/y).
  const data = useMemo(
    () => ({
      nodes: graph.topics.map((t) => ({ ...t })) as Node[],
      links: graph.edges.map((e) => ({ ...e })) as Link[],
    }),
    [graph],
  );

  return (
    <div className="space-y-3">
      <div ref={box} className="relative overflow-hidden rounded-lg border border-line bg-surface-2">
        <ForceGraph2D
          graphData={data}
          width={size.width}
          height={size.height}
          backgroundColor="rgba(0,0,0,0)"
          nodeId="id"
          nodeRelSize={6}
          linkColor={() => color("var(--border)")}
          linkWidth={1.5}
          linkDirectionalArrowLength={5}
          linkDirectionalArrowRelPos={0.9}
          linkDirectionalArrowColor={() => color("var(--text-muted)")}
          onNodeClick={(n) => onSelect(n as Node)}
          onNodeHover={(n) => setHover((n as Node) ?? null)}
          nodePointerAreaPaint={(n, paint, ctx) => {
            ctx.fillStyle = paint;
            ctx.beginPath();
            ctx.arc(n.x ?? 0, n.y ?? 0, 12, 0, 2 * Math.PI); // hit target bigger than the dot
            ctx.fill();
          }}
          nodeCanvasObject={(n, ctx, scale) => {
            const node = n as Node;
            const x = node.x ?? 0;
            const y = node.y ?? 0;
            const r = 7;
            ctx.beginPath();
            ctx.arc(x, y, r + 1.5, 0, 2 * Math.PI);
            ctx.fillStyle = color("var(--surface)"); // surface ring so overlapping dots stay distinct
            ctx.fill();
            ctx.beginPath();
            ctx.arc(x, y, r, 0, 2 * Math.PI);
            ctx.fillStyle = color(masteryVar(node.p_known, node.assessed));
            ctx.fill();
            if (node.p_known >= MASTERED) {
              ctx.fillStyle = color("var(--surface)");
              ctx.font = `bold ${10}px sans-serif`;
              ctx.textAlign = "center";
              ctx.textBaseline = "middle";
              ctx.fillText("✓", x, y + 0.5);
            }
            if (scale > 0.9 || hover?.id === node.id) {
              const size = Math.max(10 / scale, 3);
              ctx.font = `${size}px sans-serif`;
              ctx.textAlign = "center";
              ctx.textBaseline = "top";
              ctx.fillStyle = color("var(--text-2)");
              ctx.fillText(node.name, x, y + r + 3);
            }
          }}
        />
        {hover && (
          <div className="pointer-events-none absolute left-3 top-3 max-w-xs rounded-md border border-line bg-surface px-3 py-2 text-sm shadow-sm">
            <div className="font-medium">{hover.name}</div>
            <div className="text-ink-2">
              {hover.assessed ? `${pct(hover.p_known)} likely known` : "not assessed yet"}
              {hover.mastered && " · ✓ mastered"}
            </div>
            {hover.due_cards > 0 && <div className="text-muted">{hover.due_cards} cards due</div>}
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-4 text-xs text-ink-2">
        {LEGEND.map((l) => (
          <span key={l.label} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: l.color }} />
            {l.label}
          </span>
        ))}
        <span className="text-muted">Arrows point from a prerequisite to the topic that needs it.</span>
      </div>
    </div>
  );
}
