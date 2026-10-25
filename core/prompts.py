"""Load versioned prompts from prompts/<name>/v<N>.md."""

import re

from core.config import get_settings


def load_prompt(name: str, version: int | None = None) -> str:
    folder = get_settings().prompts_dir / name
    if version is None:
        versions = [int(m.group(1)) for p in folder.glob("v*.md") if (m := re.fullmatch(r"v(\d+)\.md", p.name))]
        if not versions:
            raise FileNotFoundError(f"no prompt versions in {folder}")
        version = max(versions)
    return (folder / f"v{version}.md").read_text()
