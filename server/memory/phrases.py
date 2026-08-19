"""Catch lasting preferences from short user phrases without waiting on the LLM."""

from __future__ import annotations

import re
from typing import Optional

_PROJECTS = re.compile(
    r"(?:my\s+)?projects?\s+(?:folder|directory|dir)?\s*"
    r"(?:are|is|live)?\s*(?:normally\s+)?(?:inside|in|at|:)\s+(.+)$",
    re.IGNORECASE,
)


def extract_remember_preference(text: str) -> Optional[dict[str, str]]:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return None
    match = _PROJECTS.search(cleaned.rstrip(".!"))
    if match is None:
        return None
    value = match.group(1).strip().strip("\"'")
    if not value or len(value) > 512:
        return None
    return {"key": "default_projects_directory", "value": value}
