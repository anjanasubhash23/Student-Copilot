# study-copilot

Turns course PDFs into a topic/prerequisite graph, then tutors students over it.

```
app/              # FastAPI routes
core/
├── ingest/       # pdf → chunks → topics/prereqs
├── graph/        # Neo4j reads and writes
├── tutor/        # LangGraph agent (week 2)
└── mastery/      # BKT + FSRS (week 2)
db/               # Alembic migrations for Postgres
prompts/          # versioned prompt files
eval/
data/courses/dbms/
docker-compose.yml
```

## Run

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY
docker compose up --build
```

Or locally:

```bash
docker compose up -d postgres neo4j
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

## Ingest a course

```bash
curl -F file=@data/courses/dbms/notes.pdf http://localhost:8000/courses/dbms/ingest
curl http://localhost:8000/courses/dbms/topics
```
