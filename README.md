# study-copilot

Adaptive learning platform. Turns course material into a Neo4j graph of topics, units and prerequisites, which later phases use for Graph-RAG tutoring and Bayesian Knowledge Tracing.

```
app/
├── main.py              # FastAPI app factory; owns the Neo4j driver for the app's lifetime
├── health.py            # GET /health (liveness), GET /ready (checks Neo4j)
└── settings.py          # typed config from env vars / .env, validated at startup
core/
├── llm.py               # Claude calls → pydantic objects, cached in data/cache/llm
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

- [uv](https://docs.astral.sh/uv/getting-started/installation/): `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Docker with Compose v2 (Docker Desktop, OrbStack or Colima)

uv installs Python 3.12 itself if you don't have it (pinned in `.python-version`).

## Setup

```bash
cp .env.example .env              # set NEO4J_PASSWORD (min 8 chars)
uv sync                           # creates .venv from uv.lock, including dev tools
docker compose up -d --wait       # waits until Neo4j's healthcheck passes
```

Neo4j Browser: http://localhost:7474 (user `neo4j`, password from `.env`).

`NEO4J_AUTH` only takes effect when the `neo4jdata` volume is first created. If you change `NEO4J_PASSWORD` later, either change it in Neo4j too or reset the volume with `docker compose down -v` (this deletes the graph).

## Run the API

```bash
uv run uvicorn --factory app.main:create_app --reload
curl localhost:8000/health        # {"status":"ok","version":"0.1.0"}
curl localhost:8000/ready         # {"status":"ok","neo4j":"ok"}, or 503 if Neo4j is unreachable
```

Interactive docs: http://localhost:8000/docs

## Ingest a PDF

Needs `ANTHROPIC_API_KEY` in `.env` (paid API).

```bash
uv run python scripts/ingest_pdf.py path/to/dbms.pdf --course dbms
```

The graph is also saved as JSON at `data/cache/<course>.graph.json`. Use `--dry-run` to skip Neo4j.

LLM responses are cached, so re-running on the same PDF is free. Change a prompt and only the affected calls run again.

## Checks

```bash
uv run pytest                     # tests need neither Neo4j nor an API key
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Configuration

All settings come from environment variables (or `.env`); see `.env.example`. The app refuses to start if a value is invalid, e.g. a missing or too-short `NEO4J_PASSWORD` or a non-bolt `NEO4J_URI`. Secrets are stored as `SecretStr`, so they're masked in logs and error messages.
