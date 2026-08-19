"""Catch lasting facts from short user phrases without waiting on the LLM."""

from __future__ import annotations

import re
from typing import Optional

from server.memory.keys import ALLOWED_PREFERENCE_KEYS, PREFERENCE_LABELS

_PROJECTS = re.compile(
    r"my\s+projects?\s+(?:folder|directory|dir)?\s*"
    r"(?:are|is|live)?\s*(?:normally\s+)?(?:inside|in|at|:)\s+(.+)$",
    re.IGNORECASE,
)

_FACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "owner_name",
        re.compile(
            r"\b(?:my\s+name\s+is|i am called)\s+([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,3})",
            re.I,
        ),
    ),
    ("owner_email", re.compile(r"\b(?:my\s+)?e-?mail(?:\s+address)?\s+is\s+([^\s,;]+@[^\s,;]+)", re.I)),
    (
        "owner_phone",
        re.compile(
            r"\b(?:my\s+)?(?:phone|mobile)(?:\s+number)?\s+is\s+(\+?\d[\d\s-]{8,16}\d)",
            re.I,
        ),
    ),
    (
        "owner_address",
        re.compile(r"\b(?:my\s+)?address\s+is\s+(.+?)(?:\.|$)", re.I),
    ),
    (
        "spouse_name",
        re.compile(r"\b(?:my\s+)?(?:wife(?:'s)?|spouse(?:'s)?)\s+name\s+is\s+([A-Za-z][A-Za-z'-]*)", re.I),
    ),
    (
        "child_name",
        re.compile(
            r"\b(?:my\s+)?(?:son(?:'s)?|child(?:'s)?|boy(?:'s)?)\s+name\s+is\s+([A-Za-z][A-Za-z'-]*)",
            re.I,
        ),
    ),
    (
        "preferred_language",
        re.compile(r"\b(?:speak|prefer|use)\s+(english|bangla|bengali|hindi)\b", re.I),
    ),
)

_LABELED = re.compile(
    r"(?:^|\n|;|,)\s*(name|email|phone|mobile|address|wife|spouse|son|child)\s*[:=]\s*(.+?)(?=(?:\n|;|$))",
    re.I,
)

_LABEL_TO_KEY = {
    "name": "owner_name",
    "email": "owner_email",
    "phone": "owner_phone",
    "mobile": "owner_phone",
    "address": "owner_address",
    "wife": "spouse_name",
    "spouse": "spouse_name",
    "son": "child_name",
    "child": "child_name",
}

_REMEMBER_CUE = re.compile(
    r"\b(remember|keep this in mind|store(?: these)?(?: details)?|save this|don't forget|dont forget)\b",
    re.I,
)

_QUERY = (
    (re.compile(r"\b(?:what(?:'s| is)|tell me)\s+my\s+name\b", re.I), "owner_name"),
    (re.compile(r"\b(?:what(?:'s| is)|tell me)\s+my\s+e-?mail\b", re.I), "owner_email"),
    (re.compile(r"\b(?:what(?:'s| is)|tell me)\s+my\s+(?:phone|mobile)(?:\s+number)?\b", re.I), "owner_phone"),
    (re.compile(r"\b(?:what(?:'s| is)|tell me)\s+my\s+address\b", re.I), "owner_address"),
    (
        re.compile(r"\b(?:what(?:'s| is)|who is|tell me)?\s*my\s+(?:wife|spouse)(?:'s)?\s*name\b", re.I),
        "spouse_name",
    ),
    (
        re.compile(r"\b(?:what(?:'s| is)|who is|tell me)?\s*my\s+(?:son|child|boy)(?:'s)?\s*name\b", re.I),
        "child_name",
    ),
)


def extract_remember_preference(text: str) -> Optional[dict[str, str]]:
    items = extract_remember_preferences(text)
    return items[0] if items else None


def extract_remember_preferences(text: str) -> list[dict[str, str]]:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return []
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    match = _PROJECTS.search(cleaned.rstrip(".!"))
    if match is not None:
        value = match.group(1).strip().strip("\"'")
        _add(found, seen, "default_projects_directory", value)

    for key, pattern in _FACT_PATTERNS:
        hit = pattern.search(cleaned)
        if hit is None:
            continue
        _add(found, seen, key, hit.group(1))

    for hit in _LABELED.finditer(cleaned):
        key = _LABEL_TO_KEY.get(hit.group(1).strip().lower())
        if key:
            _add(found, seen, key, hit.group(2))

    if found:
        return found
    if _REMEMBER_CUE.search(cleaned) and not found:
        return []
    return found


def extract_personal_query(text: str) -> Optional[str]:
    cleaned = " ".join((text or "").strip().split())
    for pattern, key in _QUERY:
        if pattern.search(cleaned):
            return key
    return None


def recall_spoken(key: str, value: Optional[str]) -> str:
    label = PREFERENCE_LABELS.get(key, key.replace("_", " "))
    if not value:
        return f"I don't have {label} stored yet. Tell me and ask me to remember it."
    if key == "owner_name":
        return f"Your name is {value}."
    if key == "owner_email":
        return f"Your email is {value}."
    if key == "owner_phone":
        return f"Your phone number is {value}."
    if key == "owner_address":
        return f"Your address is {value}."
    if key == "spouse_name":
        return f"Your wife's name is {value}."
    if key == "child_name":
        return f"Your son's name is {value}."
    return f"{label.capitalize()} is {value}."


def _add(found: list[dict[str, str]], seen: set[str], key: str, raw: str) -> None:
    if key not in ALLOWED_PREFERENCE_KEYS or key in seen:
        return
    value = raw.strip().strip("\"'.,;")
    if key == "owner_email":
        value = value.strip("<>")
    if key == "owner_phone":
        value = re.sub(r"[\s-]+", "", value)
    if key == "preferred_language":
        value = value.strip().lower()
        if value in {"bengali", "bangla"}:
            value = "bangla"
    if not value or len(value) > 512:
        return
    seen.add(key)
    found.append({"key": key, "value": value})
