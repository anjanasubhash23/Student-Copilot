"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Shell } from "@/components/Shell";
import { api, errorMessage, type Space } from "@/lib/api";

const STATUS: Record<Space["graph_status"], string> = {
  empty: "No sources yet",
  building: "Building the map…",
  ready: "Ready",
  failed: "Map failed",
};

function Spaces() {
  const [spaces, setSpaces] = useState<Space[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.spaces().then(setSpaces).catch((e) => setError(errorMessage(e)));
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const space = await api.createSpace(name);
      window.location.href = `/spaces/${space.id}/sources`;
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Your study spaces</h1>
        <p className="text-sm text-ink-2">A space holds the material for one course or exam.</p>
      </div>
      <form onSubmit={create} className="flex max-w-lg gap-2">
        <input
          className="input"
          placeholder='e.g. "Semester 5 DBMS"'
          required
          maxLength={200}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="btn shrink-0">Create space</button>
      </form>
      {error && <p className="text-sm text-critical">{error}</p>}
      {spaces === null ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : spaces.length === 0 ? (
        <p className="text-sm text-muted">No spaces yet. Create one, then add your notes.</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {spaces.map((s) => (
            <li key={s.id}>
              <Link href={`/spaces/${s.id}`} className="card block hover:border-accent">
                <div className="font-medium">{s.name}</div>
                <div className="mt-1 text-sm text-ink-2">{STATUS[s.graph_status]}</div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Home() {
  return (
    <Shell>
      <Spaces />
    </Shell>
  );
}
