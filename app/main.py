import shutil
from pathlib import PurePath

from fastapi import FastAPI, HTTPException, Path, UploadFile

from core.config import get_settings
from core.graph import get_topics
from core.ingest import ingest_pdf

app = FastAPI(title="study-copilot")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/courses/{course}/ingest")
def ingest(file: UploadFile, course: str = Path(pattern=r"^[a-z0-9_-]+$")):
    filename = PurePath(file.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "upload a PDF")
    dest_dir = get_settings().data_dir / "courses" / course
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return ingest_pdf(course, dest)


@app.get("/courses/{course}/topics")
def topics(course: str):
    return get_topics(course)
