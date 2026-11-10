# study-copilot

Upload your notes, slides, links or videos and get a tutor that knows what you've mastered. Study Copilot turns a study space's material into a Neo4j graph of topics, units and prerequisites, tracks how likely you are to know each topic (Bayesian Knowledge Tracing), and uses both to pick practice questions, explain things starting from the prerequisites you're weak on, and schedule flashcard reviews (FSRS).

Everything runs locally with no paid services: Neo4j Community in Docker, SQLite on disk, Ollama as the default LLM, and a Next.js web app. An external LLM API (Anthropic, OpenAI or any OpenAI-compatible server) can be used instead.

## How it fits together

```
browser ──▶ Next.js (web/, :3000) ──/api/*──▶ FastAPI (:8000) ──▶ SQLite  users, spaces, sources, jobs, questions,
                                                   │                       attempts, mastery, flashcards, reviews
                                                   ├──────────────▶ Neo4j   topics, units, chunks, prerequisites,
                                                   │                        full-text indexes (one graph per space)
                                                   └─ job worker ─▶ LLM     topic extraction, units, prerequisites,
                                                     (thread or            questions, validation, grading,
                                                      process)             explanations, flashcards
```

**Rule of thumb:** Neo4j holds *what there is to learn in a space*; SQLite holds *everything about the user and their progress*. Requests join the two.

| Store | Holds | Why |
|---|---|---|
| Neo4j (Docker) | topics, units, chunks, prerequisite edges, full-text indexes | graph traversal + text search in one place |
| SQLite (`data/app.db`) | users, sessions, study spaces, sources, the job queue, questions, attempts, mastery, flashcards, reviews | zero-setup relational data; SQL kept in `core/storage/` so it can move to PostgreSQL later |
| Disk (`data/uploads/`, `data/extracted/`) | uploaded files; each source's chunks and topics | adding a source doesn't redo the others' LLM work |

### Ingestion

Adding a source queues a job. A worker reads it (PDF, scanned PDF via OCR, PPTX, DOCX, Markdown/TXT, web page, YouTube transcript), cleans and chunks it, and asks the LLM for the topics in each chunk. Then a second job rebuilds the space's graph from all its sources: merge duplicate topics across sources → group into units → infer prerequisites → write to Neo4j. `GET /spaces/{id}/status` reports each stage.

Web links are fetched with SSRF protection: http(s) on ports 80/443 only, every redirect re-checked, private and internal addresses refused (checked again on the address actually connected to), 20 MB cap, HTML/text/PDF only. Uploads are typed by content, not by file name.

### The learning loop

- **Diagnostic** (10 questions): picks the unasked topic whose answer tells most (uncertain, well connected). A right answer also raises the topic's prerequisites, and a wrong one lowers the topics built on it, halving per hop, so a short quiz colours the whole map.
- **Practice**: the weakest unmastered topic whose prerequisites are probably known (or any topic you pick on the map).
- **Questions** are generated the first time a topic is practised, then reused. Each one cites the chunk it came from and passes structural checks plus a second LLM check. Numerical questions are kept only if their generated Python solution, run in a sandbox, reproduces the answer. Rejected questions are stored with the reasons.
- **Marking**: MCQ by key, multiple-select with partial credit, numerical by range, short answers by rubric (LLM).
- **Mastery**: BKT per topic with a guess rate per question type (spec section 6). Mastered = p ≥ 0.95.
- **Explain** (Graph-RAG): full-text search finds the topic, then the prerequisites within 2 hops you haven't mastered, then their chunks. The answer covers those prerequisites first and cites `[n]` sources with page, slide, section or timestamp.
- **Flashcards** are generated per topic after its first practice (a background job) and reviewed with FSRS.

### The graph in Neo4j

```
(:Unit)-[:HAS_TOPIC {position}]->(:Topic)
(:Chunk)-[:ABOUT]->(:Topic)
(:Topic)-[:PREREQUISITE_OF {confidence, reason, extracted_by}]->(:Topic)   learn the first, then the second
```

Every node has `space_id`, and topic and unit ids are `{space_id}:{slug}`. Every query filters on `space_id`; `tests/test_graph_scoping.py` fails if one doesn't. `extracted_by` records the model and a hash of the prompt file (e.g. `ollama/llama3.1:8b prereqs@1a2b3c4d`); questions and flashcards record theirs too.

### Code layout

```
app/
├── main.py              # FastAPI app factory: migrations, Neo4j driver, in-process worker, error mapping
├── deps.py              # per-request SQLite connection, current user, owned-space lookup
├── health.py            # GET /health, GET /ready
├── settings.py          # typed config from env vars / .env, validated at startup
└── routes/              # auth, spaces (+ sources, status, graph), learning, flashcards
core/
├── llm.py               # the one LLM wrapper: structured output or text, cached on disk
├── auth/passwords.py    # scrypt password hashes
├── sources/             # detect.py (sniff uploads), fetch.py (SSRF-safe), pdf.py (+OCR), office.py, text.py, web.py, youtube.py
├── ingest/              # clean, chunk, topics, merge, units, prereqs, pipeline, recall (eval scoring)
├── graph/               # client, ids, writer, queries (space-scoped), space_map (in-memory topic graph)
├── questions/           # schema, bank (lazy generation), validate, numeric_runner (sandbox), flashcards, excerpts
├── marking/marking.py   # key, range, rubric
├── mastery/             # bkt.py, select.py (diagnostic/practice topic choice), fsrs.py, progress.py
├── tutor/               # answers.py, diagnostic.py, practice.py, explain.py
├── spaces/              # study space model + repository protocol
└── storage/             # SQLite: migrations, repositories, job queue, file store
workers/                 # job handlers (tasks.py) and the worker loop (run.py)
prompts/                 # one file per LLM step
scripts/ingest.py        # CLI: add a file or link to a space and ingest it now
eval/                    # corpora.md, run_eval.py (topic recall/precision)
web/                     # Next.js app
tests/
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/): `brew install uv`
- Docker with Compose v2: Docker Desktop, OrbStack or Colima (all free for personal use)
- [Node.js](https://nodejs.org) 20.9 or newer, for the web app: `brew install node`
- Optional, for local LLMs: [Ollama](https://ollama.com): `brew install ollama`
- Optional, for scanned PDFs: Tesseract OCR: `brew install tesseract`

uv installs Python 3.12 itself if you don't have it (pinned in `.python-version`). SQLite ships with Python.

## Setup

```bash
cp .env.example .env              # set NEO4J_PASSWORD (min 8 chars); pick LLM_PROVIDER
uv sync                           # creates .venv from uv.lock, including dev tools
docker compose up -d --wait       # waits until Neo4j's healthcheck passes
cd web && npm install && cd ..    # web app dependencies
```

After pulling changes that add Python dependencies, run `uv sync` again (and `uv lock` if `uv.lock` is out of date).

Neo4j Browser: http://localhost:7474 (user `neo4j`, password from `.env`).

`NEO4J_AUTH` only takes effect when the `neo4jdata` volume is first created. If you change `NEO4J_PASSWORD` later, either change it in Neo4j too or reset the volume with `docker compose down -v` (this deletes the graph).

The SQLite database is created and migrated automatically when the API starts.

### LLM provider

Set `LLM_PROVIDER` in `.env`. Only the chosen provider's settings are needed.

**Ollama (default, free, local).** Runs natively rather than in Docker, because Docker on macOS can't use the Apple GPU.

```bash
brew services start ollama        # or `ollama serve` in a separate terminal
ollama pull llama3.1:8b           # default model; set LLM_MODEL to use another
```

An 8B model works for topic extraction but writes weaker questions; a larger local model or an API model makes a noticeable difference to question quality and validation pass rates.

**Anthropic:** `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` (`LLM_MODEL` defaults to `claude-sonnet-5-5`).

**OpenAI or OpenAI-compatible:** `LLM_PROVIDER=openai`, `LLM_MODEL=...`, and either `OPENAI_API_KEY=...` or `OPENAI_BASE_URL=...` for a local server such as LM Studio.

## Run it

Two terminals:

```bash
uv run uvicorn --factory app.main:create_app --reload     # API on :8000, with the job worker in a thread
cd web && npm run dev                                      # web app on :3000
```

Open http://localhost:3000, create an account, create a space, add sources, then take the diagnostic.

- API docs: http://localhost:8000/docs. API clients can sign in with `POST /auth/login` and send the returned token as `Authorization: Bearer <token>`.
- The API starts without the LLM; jobs and learning requests that need it report that it isn't reachable. A failed source can be retried from the Sources tab.
- To run the worker as its own process instead (e.g. so `--reload` doesn't interrupt long jobs), set `RUN_WORKER=false` and run `uv run python -m workers.run`. Several workers can share the queue.
- The web app proxies `/api/*` to `API_URL` (default `http://localhost:8000`, see `web/.env.example`), so the session cookie is same-origin and there's no CORS to configure.

```bash
curl localhost:8000/health        # {"status":"ok","version":"0.1.0"}
curl localhost:8000/ready         # {"status":"ok","neo4j":"ok","sqlite":"ok"}, or 503 naming what's down
```

## API

| Method | Path | Does |
|---|---|---|
| POST | `/auth/register`, `/auth/login`, `/auth/logout` | Accounts and sessions (HttpOnly cookie, or Bearer token) |
| GET | `/auth/me` | The signed-in user |
| POST / GET | `/spaces` | Create / list your study spaces |
| GET / DELETE | `/spaces/{id}` | A space / delete it with its graph, files and rows |
| POST | `/spaces/{id}/sources` | Upload a file (multipart) → queues ingestion |
| POST | `/spaces/{id}/sources/link` | Add a web page or YouTube video → queues ingestion |
| POST | `/spaces/{id}/sources/{source_id}/retry` | Re-queue a failed source |
| DELETE | `/spaces/{id}/sources/{source_id}` | Remove a source; the graph is rebuilt |
| GET | `/spaces/{id}/status` | Ingestion progress per source, and the map's build stage |
| GET | `/spaces/{id}/graph` | Units, topics with your mastery, prerequisite edges |
| POST | `/spaces/{id}/diagnostic` | Start the diagnostic; returns the first question |
| POST | `/spaces/{id}/diagnostic/{diagnostic_id}/answer` | Answer; returns the result and the next question |
| POST | `/spaces/{id}/practice/next` | Next question (optionally for a chosen topic) |
| POST | `/spaces/{id}/practice/answer` | `{question_id, response}` → mark, solution, updated mastery |
| POST | `/spaces/{id}/explain` | `{question}` → explanation with citations |
| GET | `/spaces/{id}/progress` | Mastered over time, weakest topics, reviews due |
| GET | `/spaces/{id}/flashcards/due` | Cards due for review, then new ones |
| POST | `/spaces/{id}/flashcards/generate` | Queue flashcards for a topic |
| POST | `/flashcards/{id}/review` | `{rating: again/hard/good/easy}` → next due date |

Spaces are private: anything in another user's space answers 404.

## Ingest from the command line

Runs the same jobs as the worker, inline:

```bash
uv run python scripts/ingest.py notes.pdf --new-space "Semester 5 DBMS" --owner you@example.com
uv run python scripts/ingest.py https://youtu.be/VIDEO_ID --space <space-id>
uv run python scripts/ingest.py notes.pdf --dry-run       # graph JSON only; no SQLite or Neo4j
```

`--owner` (an existing account's email) makes the space visible in the web app. The graph is saved as JSON at `data/cache/<space-id>.graph.json`. To check topic quality against a hand-made label list, see [eval/corpora.md](eval/corpora.md).

LLM responses are cached per provider and model, so re-running on the same material is free. Change a prompt and only the affected calls run again.

## Checks

```bash
uv run pytest                     # needs no Neo4j, Ollama or API key
uv run ruff check .
uv run ruff format --check .
uv run mypy
cd web && npm run typecheck       # TypeScript
```

## Configuration

All settings come from environment variables (or `.env`); see `.env.example`, which documents each one (limits per space, worker mode, OCR language, session lifetime). The app refuses to start if a value is invalid, e.g. a missing or too-short `NEO4J_PASSWORD`, a non-bolt `NEO4J_URI`, or `LLM_PROVIDER=anthropic` without `ANTHROPIC_API_KEY`. Secrets are stored as `SecretStr`, so they're masked in logs and error messages.

## Where this differs from the spec

The spec (`../project.md`) names some hosted services; this build keeps everything local and free:

| Spec | Here | Why |
|---|---|---|
| Postgres + pgvector (Supabase) | SQLite | zero setup; SQL is confined to `core/storage/` |
| Redis + arq | a job queue table in SQLite | no extra service; atomic claims let several workers share it |
| Supabase Auth | email + password, scrypt hashes, server-side sessions | no external service |
| Supabase Storage | files under `data/` | local |
| bge-small embeddings + vector indexes | Neo4j full-text (Lucene) indexes | no torch download; good enough to find a topic by its terms. Embedding-based merge and retrieval are a later improvement |
| LangGraph tutor | plain functions per step | the API already separates the steps, so there's no conversation state to manage |
| Langfuse traces, cost per job | not yet | |

## Security notes

- Uploaded and fetched text is treated as content: prompts quote it inside delimiters that it can't close, and tell the model to ignore instructions in it.
- Generated numerical solutions run in a separate Python process with an empty environment and a 5-second timeout. An audit hook blocks network access, starting processes, native code and file access outside the standard library, and CPU and file-size limits apply. This is defence in depth for model-written code, not a hardened sandbox; don't expose the app to untrusted users without stronger isolation (e.g. a container with no network).
- Deleting a space deletes its graph nodes, rows (by cascade) and files.
