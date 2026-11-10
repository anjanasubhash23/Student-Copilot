"""Where uploaded files and per-source extraction results are kept on disk."""

import shutil
from pathlib import Path

from core.ingest.schema import SourceExtraction


class FileStore:
    def __init__(self, data_dir: Path) -> None:
        self.uploads = data_dir / "uploads"
        self.extracted = data_dir / "extracted"

    def save_upload(self, space_id: str, source_id: str, extension: str, data: bytes) -> Path:
        path = self.uploads / space_id / f"{source_id}{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def _extraction_path(self, space_id: str, source_id: str) -> Path:
        return self.extracted / space_id / f"{source_id}.json"

    def save_extraction(self, space_id: str, extraction: SourceExtraction) -> None:
        path = self._extraction_path(space_id, extraction.source.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(extraction.model_dump_json())
        tmp.replace(path)  # atomic, so a build never reads a half-written file

    def load_extraction(self, space_id: str, source_id: str) -> SourceExtraction | None:
        path = self._extraction_path(space_id, source_id)
        return SourceExtraction.model_validate_json(path.read_text()) if path.exists() else None

    def delete_source(self, space_id: str, source_id: str, storage_path: str | None) -> None:
        self._extraction_path(space_id, source_id).unlink(missing_ok=True)
        if storage_path:
            Path(storage_path).unlink(missing_ok=True)

    def delete_space(self, space_id: str) -> None:
        for root in (self.uploads, self.extracted):
            shutil.rmtree(root / space_id, ignore_errors=True)
