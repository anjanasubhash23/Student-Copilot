# study-copilot

Adaptive learning platform. Turns course material into a Neo4j graph of topics, units and prerequisites, which later phases use for Graph-RAG tutoring and Bayesian Knowledge Tracing.

Everything runs locally with no paid services: Neo4j Community in Docker, SQLite on disk, and Ollama as the default LLM. An external LLM API (Anthropic, OpenAI or any OpenAI-compatible server) can be used instead.

## Where data lives

| Store | Holds | Why |
|---|---|---|
| Neo4j (Docker) | topics, units, chunks, prerequisite edges, vector indexes | graph traversal + vector search in one place |
| SQLite (`data/app.db`) | users, study spaces, questions, attempts, mastery, flashcards | zero-setup relational data; behind repository interfaces so it can move to PostgreSQL later |

```
app/
├── main.py              # FastAPI app factory; migrates SQLite and owns the Neo4j driver
├── health.py            # GET /health (liveness), GET /ready (checks Neo4j and SQLite)
└── settings.py          # typed config from env vars / .env, validated at startup
core/
├── llm.py               # provider-agnostic LLM calls (LangChain) → pydantic objects, cached on disk
├── spaces/              # study spaces: model + StudySpaceRepository protocol
├── storage/
│   ├── sqlite.py        # SQLite connection + schema migrations (PRAGMA user_version)
│   └── spaces.py        # SqliteStudySpaceRepository
├── sources/pdf.py       # PDF → pages
├── ingest/
│   ├── schema.py        # Page, Chunk, Topic, Unit, Prereq, CourseGraph
│   ├── clean.py         # strip headers/footers/page numbers
│   ├── chunk.py         # pages → overlapping chunks
│   ├── topics.py        # chunk → topics (LLM)
│   ├── merge.py         # dedupe topics across chunks
│   ├── units.py         # topics → ordered units (LLM)
│   ├── prereqs.py       # topics → prerequisite edges (LLM), cycles removed
│   └── pipeline.py      # runs the stages above
├── graph/
│   ├── client.py        # Neo4j driver
│   ├── writer.py        # CourseGraph → Neo4j
│   └── queries.py       # units, topic detail, learning path
├── questions/           # later phase: question generation
├── tutor/               # later phase: LangGraph tutor
└── mastery/             # later phase: BKT
prompts/                 # topics.md, units.md, prereqs.md
scripts/ingest_pdf.py    # CLI entry point
eval/corpora.md          # PDFs used to judge ingest quality (files in eval/data/)
tests/
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/): `brew install uv`
- Docker with Compose v2: Docker Desktop, OrbStack or Colima (all free for personal use)
- Optional, for local LLMs: [Ollama](https://ollama.com): `brew install ollama`

uv installs Python 3.12 itself if you don't have it (pinned in `.python-version`). SQLite ships with Python; nothing to install.

## Setup

```bash
cp .env.example .env              # set NEO4J_PASSWORD (min 8 chars); pick LLM_PROVIDER
uv sync                           # creates .venv from uv.lock, including dev tools
docker compose up -d --wait       # waits until Neo4j's healthcheck passes
```

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

**Anthropic:** `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` (`LLM_MODEL` defaults to `claude-sonnet-5-5`).

**OpenAI or OpenAI-compatible:** `LLM_PROVIDER=openai`, `LLM_MODEL=...`, and either `OPENAI_API_KEY=...` or `OPENAI_BASE_URL=...` for a local server such as LM Studio.

## Run the API

```bash
uv run uvicorn --factory app.main:create_app --reload
curl localhost:8000/health        # {"status":"ok","version":"0.1.0"}
curl localhost:8000/ready         # {"status":"ok","neo4j":"ok","sqlite":"ok"}, or 503 naming what's down
```

Interactive docs: http://localhost:8000/docs

The API doesn't need the LLM to start, so Ollama can be off.

## Ingest a PDF

Uses the configured LLM provider.

```bash
uv run python scripts/ingest_pdf.py path/to/dbms.pdf --course dbms
```

The graph is also saved as JSON at `data/cache/<course>.graph.json`. Use `--dry-run` to skip Neo4j.

LLM responses are cached per provider and model, so re-running on the same PDF is free. Change a prompt and only the affected calls run again.

## Checks

```bash
uv run pytest                     # needs no Neo4j, Ollama or API key
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Configuration

All settings come from environment variables (or `.env`); see `.env.example`. The app refuses to start if a value is invalid, e.g. a missing or too-short `NEO4J_PASSWORD`, a non-bolt `NEO4J_URI`, or `LLM_PROVIDER=anthropic` without `ANTHROPIC_API_KEY`. Secrets are stored as `SecretStr`, so they're masked in logs and error messages.
