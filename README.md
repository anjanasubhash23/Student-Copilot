# study-copilot

Turns a course PDF into a graph of topics, units, and prerequisites in Neo4j.

```
app/settings.py          # config from .env
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
└── graph/
    ├── client.py        # Neo4j driver
    ├── writer.py        # CourseGraph → Neo4j
    └── queries.py       # units, topic detail, learning path
prompts/                 # topics.md, units.md, prereqs.md
scripts/ingest_pdf.py    # CLI entry point
eval/corpora.md          # PDFs used to judge ingest quality (files in eval/data/)
tests/
```

## Run

```bash
cp .env.example .env              # add ANTHROPIC_API_KEY
docker compose up -d              # Neo4j at http://localhost:7474
pip install -e ".[dev]"
python scripts/ingest_pdf.py path/to/dbms.pdf --course dbms
```

The graph is also saved as JSON at `data/cache/<course>.graph.json`. Use `--dry-run` to skip Neo4j.

LLM responses are cached, so re-running on the same PDF is free. Change a prompt and only the affected calls run again.

## Test

```bash
pytest
```
