// Typed client for the FastAPI backend, reached through the /api proxy (see next.config.ts).

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: "same-origin" });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).join("; ")
      : typeof detail === "string"
        ? detail
        : `request failed (${res.status})`;
    throw new ApiError(res.status, message);
  }
  return body as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

// Types mirror the API's response models.

export type User = { id: string; email: string; created_at: string };

export type Space = {
  id: string;
  name: string;
  created_at: string;
  exam_style: string;
  graph_status: "empty" | "building" | "ready" | "failed";
  graph_error: string | null;
};

export type Source = {
  id: string;
  kind: "pdf" | "pptx" | "docx" | "text" | "web" | "youtube";
  name: string;
  uri: string | null;
  pages: number | null;
  status: "queued" | "processing" | "ready" | "failed";
  stage: string | null;
  progress: number;
  error: string | null;
  created_at: string;
};

export type SpaceStatus = {
  graph: { status: string; stage: string | null; error: string | null };
  sources: Source[];
};

export type MapTopic = {
  id: string;
  name: string;
  summary: string;
  unit_id: string | null;
  p_known: number;
  assessed: boolean;
  mastered: boolean;
  attempts: number;
  due_cards: number;
  prerequisites: string[];
};

export type SpaceGraph = {
  units: { id: string; name: string; order: number }[];
  topics: MapTopic[];
  edges: { source: string; target: string; confidence: number }[];
};

export type QuestionType = "mcq" | "msq" | "short" | "numeric";

export type Question = { id: string; topic_id: string; type: QuestionType; stem: string; options: string[] };

export type AnswerResponse = { choice?: number; choices?: number[]; value?: number; text?: string };

export type TopicMastery = { topic_id: string; name: string; p_known: number; mastered: boolean };

export type AnswerResult = {
  mark: { correct: boolean; score: number; feedback: string };
  reveal: {
    correct: number[];
    answer: string;
    range: [number, number] | null;
    explanation: string;
    chunk_id: string;
  };
  mastery: TopicMastery;
  also_updated: TopicMastery[];
  source: { name: string; location: string } | null;
};

export type DiagnosticStep = {
  diagnostic_id: string;
  number: number;
  total: number;
  done: boolean;
  question: Question | null;
};

export type Citation = { n: number; chunk_id: string; source: string; location: string; topic: string | null };

export type Explanation = {
  answer: string;
  topic: string | null;
  covered_prerequisites: string[];
  citations: Citation[];
};

export type Card = { id: string; front: string; back: string; topic_id: string; topic: string | null; new: boolean };

export type Progress = {
  topics: number;
  mastered: number;
  assessed: number;
  mastered_over_time: { date: string; mastered: number }[];
  recent_accuracy: number | null;
  attempts: number;
  weakest: { id: string; name: string; p_known: number }[];
  due_for_review: { id: string; name: string; cards: number }[];
  reviewed_today: number;
};

export const api = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) => request<{ user: User }>("/auth/login", json({ email, password })),
  register: (email: string, password: string) =>
    request<{ user: User }>("/auth/register", json({ email, password })),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  spaces: () => request<Space[]>("/spaces"),
  createSpace: (name: string) => request<Space>("/spaces", json({ name })),
  space: (id: string) => request<Space>(`/spaces/${id}`),
  deleteSpace: (id: string) => request<void>(`/spaces/${id}`, { method: "DELETE" }),

  status: (id: string) => request<SpaceStatus>(`/spaces/${id}/status`),
  upload: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Source>(`/spaces/${id}/sources`, { method: "POST", body: form });
  },
  addLink: (id: string, url: string) => request<Source>(`/spaces/${id}/sources/link`, json({ url })),
  retrySource: (id: string, sourceId: string) =>
    request<Source>(`/spaces/${id}/sources/${sourceId}/retry`, { method: "POST" }),
  deleteSource: (id: string, sourceId: string) =>
    request<void>(`/spaces/${id}/sources/${sourceId}`, { method: "DELETE" }),

  graph: (id: string) => request<SpaceGraph>(`/spaces/${id}/graph`),

  startDiagnostic: (id: string) => request<DiagnosticStep>(`/spaces/${id}/diagnostic`, { method: "POST" }),
  answerDiagnostic: (id: string, diagnosticId: string, questionId: string, response: AnswerResponse) =>
    request<{ result: AnswerResult; next: DiagnosticStep }>(
      `/spaces/${id}/diagnostic/${diagnosticId}/answer`,
      json({ question_id: questionId, response }),
    ),

  practiceNext: (id: string, topicId?: string) =>
    request<{ question: Question | null; topic: string | null; message: string | null }>(
      `/spaces/${id}/practice/next`,
      json({ topic_id: topicId ?? null }),
    ),
  practiceAnswer: (id: string, questionId: string, response: AnswerResponse) =>
    request<AnswerResult>(`/spaces/${id}/practice/answer`, json({ question_id: questionId, response })),

  explain: (id: string, question: string) => request<Explanation>(`/spaces/${id}/explain`, json({ question })),

  dueCards: (id: string) => request<{ cards: Card[] }>(`/spaces/${id}/flashcards/due`),
  makeCards: (id: string, topicId: string) =>
    request<{ queued: boolean }>(`/spaces/${id}/flashcards/generate`, json({ topic_id: topicId })),
  review: (cardId: string, rating: "again" | "hard" | "good" | "easy") =>
    request<{ due_at: string }>(`/flashcards/${cardId}/review`, json({ rating })),

  progress: (id: string) => request<Progress>(`/spaces/${id}/progress`),
};

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
