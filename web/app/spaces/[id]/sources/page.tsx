"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage, type SpaceStatus } from "@/lib/api";

const KIND: Record<string, string> = {
  pdf: "PDF",
  pptx: "Slides",
  docx: "Word",
  text: "Text",
  web: "Web page",
  youtube: "YouTube",
};

export default function SourcesPage() {
  const { id } = useParams<{ id: string }>();
  const [status, setStatus] = useState<SpaceStatus | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => api.status(id).then(setStatus).catch((e) => setError(errorMessage(e))), [id]);

  const working =
    status !== null &&
    (status.graph.status === "building" || status.sources.some((s) => s.status === "queued" || s.status === "processing"));

  useEffect(() => {
    refresh();
  }, [refresh]);
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [working, refresh]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div className="card space-y-4">
        <div>
          <h2 className="font-semibold">Add material</h2>
          <p className="text-sm text-ink-2">PDF (including scanned), PowerPoint, Word, Markdown or text files, web pages, and YouTube videos with captions.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".pdf,.pptx,.docx,.md,.markdown,.txt"
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              run(async () => {
                for (const f of files) await api.upload(id, f);
              });
            }}
          />
          <button className="btn" disabled={busy} onClick={() => fileInput.current?.click()}>
            Upload files
          </button>
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              await api.addLink(id, url);
              setUrl("");
            });
          }}
        >
          <input className="input" type="url" placeholder="https://… (web page or YouTube video)" value={url} onChange={(e) => setUrl(e.target.value)} required />
          <button className="btn-ghost shrink-0" disabled={busy}>
            Add link
          </button>
        </form>
        {error && <p className="text-sm text-critical">{error}</p>}
      </div>

      {status && (
        <div className="card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Topic map</h2>
            <span className="text-sm text-ink-2">
              {status.graph.status === "building"
                ? `Building: ${status.graph.stage ?? "waiting"}…`
                : status.graph.status === "ready"
                  ? "Ready"
                  : status.graph.status === "failed"
                    ? status.graph.error
                    : "Waiting for sources"}
            </span>
          </div>
          {status.graph.status === "ready" && !working && (
            <div className="flex gap-2">
              <Link href={`/spaces/${id}`} className="btn">
                See the map
              </Link>
              <Link href={`/spaces/${id}/diagnostic`} className="btn-ghost">
                Take the diagnostic
              </Link>
            </div>
          )}
          <ul className="divide-y divide-line">
            {status.sources.length === 0 && <li className="py-2 text-sm text-muted">No sources yet.</li>}
            {status.sources.map((s) => (
              <li key={s.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium" title={s.uri ?? s.name}>
                    {s.name}
                  </div>
                  <div className="text-xs text-muted">
                    {KIND[s.kind]}
                    {s.pages ? ` · ${s.pages} ${s.kind === "youtube" ? "minutes" : s.kind === "pptx" ? "slides" : "pages"}` : ""}
                  </div>
                  {s.status === "processing" && (
                    <div className="mt-2 w-56">
                      <div className="text-xs text-ink-2">
                        {s.stage}
                        {s.stage === "finding topics" && ` · ${Math.round(s.progress * 100)}%`}
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.max(5, s.progress * 100)}%` }} />
                      </div>
                    </div>
                  )}
                  {s.status === "failed" && <div className="mt-1 text-xs text-critical">{s.error}</div>}
                </div>
                <div className="flex shrink-0 items-center gap-2 text-sm">
                  <span className={s.status === "ready" ? "text-good" : s.status === "failed" ? "text-critical" : "text-ink-2"}>
                    {{ queued: "Queued", processing: "Reading", ready: "✓ Ready", failed: "✗ Failed" }[s.status]}
                  </span>
                  {s.status === "failed" && (
                    <button className="btn-ghost px-2 py-1 text-xs" disabled={busy} onClick={() => run(() => api.retrySource(id, s.id))}>
                      Retry
                    </button>
                  )}
                  <button
                    className="btn-ghost px-2 py-1 text-xs"
                    disabled={busy}
                    onClick={() => confirm(`Remove ${s.name}?`) && run(() => api.deleteSource(id, s.id))}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
