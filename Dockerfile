# API and job worker (same image; the worker runs `python -m workers.run`).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Tesseract reads scanned PDFs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

WORKDIR /app
# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY core ./core
COPY workers ./workers
COPY prompts ./prompts
COPY scripts ./scripts
COPY eval/run_eval.py eval/corpora.md ./eval/
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 copilot && mkdir -p /app/data && chown copilot /app/data
USER copilot

ENV PATH=/app/.venv/bin:$PATH \
    DATA_DIR=/app/data \
    SQLITE_PATH=/app/data/app.db \
    CACHE_DIR=/app/data/cache
VOLUME /app/data
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
