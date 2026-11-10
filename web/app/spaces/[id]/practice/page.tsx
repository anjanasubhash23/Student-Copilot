"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { QuestionCard } from "@/components/QuestionCard";
import { api, errorMessage, type Question } from "@/lib/api";

function Practice() {
  const { id } = useParams<{ id: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const topicId = params.get("topic") ?? undefined;
  const [question, setQuestion] = useState<Question | null>(null);
  const [topic, setTopic] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (focus?: string) => {
      setLoading(true);
      setError(null);
      try {
        const r = await api.practiceNext(id, focus);
        setQuestion(r.question);
        setTopic(r.topic);
        setMessage(r.message);
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setLoading(false);
      }
    },
    [id],
  );

  useEffect(() => {
    load(topicId);
  }, [load, topicId]);

  return (
    <div className="max-w-2xl space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-2">
          {topic ? (
            <>
              Topic: <span className="font-medium text-ink">{topic}</span>
              {!topicId && " (your weakest topic that's ready to learn)"}
            </>
          ) : (
            "Practice"
          )}
        </p>
        {topicId && (
          <button className="text-sm text-accent hover:underline" onClick={() => router.replace(`/spaces/${id}/practice`)}>
            Let the tutor pick
          </button>
        )}
      </div>
      {error && <p className="text-sm text-critical">{error}</p>}
      {loading ? (
        <div className="card text-sm text-muted">Finding a question… (writing new ones from your material can take a minute)</div>
      ) : question ? (
        <QuestionCard
          key={question.id}
          question={question}
          onSubmit={(response) => api.practiceAnswer(id, question.id, response)}
          onNext={() => load(topicId)}
        />
      ) : (
        <div className="card space-y-3">
          <p className="text-sm">{message ?? "No question available."}</p>
          <Link href={`/spaces/${id}`} className="btn-ghost">
            Back to the map
          </Link>
        </div>
      )}
    </div>
  );
}

export default function PracticePage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <Practice />
    </Suspense>
  );
}
