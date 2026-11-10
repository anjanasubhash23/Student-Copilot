"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Shell } from "@/components/Shell";
import { api, type Space } from "@/lib/api";

const TABS = [
  ["", "Map"],
  ["/sources", "Sources"],
  ["/diagnostic", "Diagnostic"],
  ["/practice", "Practice"],
  ["/explain", "Ask"],
  ["/flashcards", "Flashcards"],
  ["/progress", "Progress"],
] as const;

export default function SpaceLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const path = usePathname();
  const router = useRouter();
  const [space, setSpace] = useState<Space | null>(null);

  useEffect(() => {
    api.space(id).then(setSpace).catch(() => router.replace("/"));
  }, [id, router]);

  const base = `/spaces/${id}`;
  return (
    <Shell>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/" className="text-sm text-muted hover:underline">
            ← All spaces
          </Link>
          <h1 className="text-xl font-semibold">{space?.name ?? "…"}</h1>
        </div>
        <button
          className="btn-ghost text-critical"
          onClick={async () => {
            if (!space || !confirm(`Delete "${space.name}" with all its sources, progress and flashcards?`)) return;
            await api.deleteSpace(id);
            router.replace("/");
          }}
        >
          Delete space
        </button>
      </div>
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map(([suffix, label]) => {
          const href = base + suffix;
          const active = suffix === "" ? path === base : path.startsWith(href);
          return (
            <Link
              key={label}
              href={href}
              className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
                active ? "border-accent font-medium text-ink" : "border-transparent text-ink-2 hover:text-ink"
              }`}
            >
              {label}
            </Link>
          );
        })}
      </nav>
      {children}
    </Shell>
  );
}
