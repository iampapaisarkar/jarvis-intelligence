"""Deterministic multi-open plans. The small CPU model often drops the second action."""

from __future__ import annotations

import re
from typing import Optional

from server.ai.intent import ParsedIntent
from server.tools.catalog import (
    canonical_application_name,
    normalize_project_kind,
    resolve_application_alias,
)
from server.tools.web import google_search_url, youtube_search_url

_LEAD = re.compile(
    r"^(?:please\s+|can you\s+|could you\s+|would you\s+|i want you to\s+|i need you to\s+)+",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"\s+(?:and|&|plus|এবং|then|, then)\s+|\s*,\s+", re.IGNORECASE)
_EDITORS = r"(?:visual studio code|vs\s*code|vscode|code)"
_IN_EDITOR = re.compile(
    rf"^(?:open|kholo|khol)\s+(?:the\s+)?(?P<name>.+?)\s+"
    rf"(?:project\s+)?(?:in|on|with|inside)\s+(?P<app>{_EDITORS})\s*$",
    re.IGNORECASE,
)
_PROJECT = re.compile(
    rf"^(?:open|kholo|khol)\s+(?:the\s+)?(?P<name>.+?)\s+project"
    rf"(?:\s+(?:in|on|with)\s+(?P<app>{_EDITORS}))?\s*$",
    re.IGNORECASE,
)
_OPEN = re.compile(r"^(?:open|kholo|khol)\s+(?:the\s+)?(?P<name>.+?)\s*$", re.IGNORECASE)


def parse_open_web(
    text: str,
    *,
    target: str,
    session_id: str,
) -> Optional[list[ParsedIntent]]:
    cleaned = _LEAD.sub("", " ".join((text or "").strip().split())).strip(" .!?")
    cleaned = cleaned.replace("'", "").replace('"', "")
    if not cleaned:
        return None
    match = _YOUTUBE_IN.match(cleaned) or _YOUTUBE_FOR.match(cleaned)
    if match:
        query = _clean_name(match.group("query"))
        if not query:
            return None
        url = youtube_search_url(query)
        spoken = f"Opening {query} on YouTube."
        return [_open_url_intent(url, spoken, target, session_id)]
    match = _GOOGLE.match(cleaned)
    if match:
        query = _clean_name(next(group for group in match.groups() if group))
        if not query:
            return None
        url = google_search_url(query)
        spoken = f"Searching Google for {query}."
        return [_open_url_intent(url, spoken, target, session_id)]
    return None


def parse_create_project(
    text: str,
    *,
    target: str,
    session_id: str,
) -> Optional[list[ParsedIntent]]:
    cleaned = _LEAD.sub("", " ".join((text or "").strip().split())).strip(" .!?")
    cleaned = re.sub(r"^i told you(?: to)?\s+", "", cleaned, flags=re.IGNORECASE)
    kind_match = _CREATE_KIND.search(cleaned)
    if kind_match is None:
        return None
    raw_kind = re.sub(r"\s+", " ", kind_match.group("kind").strip().lower())
    kind = normalize_project_kind(raw_kind)
    default_name = "app" if kind == "generic" else f"{kind}-app"
    name_match = _CREATE_NAME.search(cleaned)
    name = _clean_name(name_match.group("name")) if name_match else default_name
    if not name or name.lower() in {"project", "app", "application"}:
        name = default_name
    spoken = f"Creating the {kind} project {name}."
    return [
        ParsedIntent(
            type="tool_call",
            message=spoken,
            spoken_reply=spoken,
            session_id=session_id,
            tool="create_project",
            target=target,  # type: ignore[arg-type]
            arguments={"name": name, "kind": kind, "open_in": "Visual Studio Code"},
            risk="low",
            requires_confirmation=False,
        )
    ]


_CREATE_KIND = re.compile(
    r"\b(?:create|make|start|banao)\s+(?:a |an |me a )?(?:new )?"
    r"(?P<kind>node\.?js|nodejs|node\s*js|not\s+just|no\s+js|"
    r"react\s*js|next\s*js|vue\s*js|type\s*script|typescript|"
    r"web\s+app|website|python|django|flask|golang|react|next|vue|"
    r"html|rust|java|angular|javascript|node|go|web)\b",
    re.IGNORECASE,
)
_CREATE_NAME = re.compile(
    r"\b(?:called|named|titled|title is|name is|project title is)\s+(?P<name>.+)$",
    re.IGNORECASE,
)
_YOUTUBE_IN = re.compile(
    r"^(?:open|play|search|find|put on)\s+(?:the\s+)?(?P<query>.+?)\s+"
    r"(?:in|on|from|inside)\s+(?:you\s*tube|youtube|utube|u\s*tube)\s*$",
    re.IGNORECASE,
)
_YOUTUBE_FOR = re.compile(
    r"^(?:open|play|search)\s+(?:you\s*tube|youtube|utube)\s+"
    r"(?:for\s+|and\s+(?:play|search(?:\s+for)?)\s+)?(?P<query>.+)$",
    re.IGNORECASE,
)
_GOOGLE = re.compile(
    r"^(?:search(?:\s+for)?\s+(?P<q1>.+?)\s+on\s+google|"
    r"google\s+search(?:\s+for)?\s+(?P<q2>.+)|"
    r"look up\s+(?P<q3>.+))$",
    re.IGNORECASE,
)


def parse_compound_opens(
    text: str,
    *,
    target: str,
    session_id: str,
) -> Optional[list[ParsedIntent]]:
    cleaned = _LEAD.sub("", " ".join((text or "").strip().split())).strip(" .!?")
    if not cleaned:
        return None
    parts = [part.strip(" .!?") for part in _SPLIT.split(cleaned) if part.strip()]
    if not parts:
        return None
    steps: list[ParsedIntent] = []
    for part in parts:
        step = _clause_to_intent(part, target=target, session_id=session_id)
        if step is None:
            return None
        steps.append(step)
    if len(steps) >= 2:
        return steps
    if steps and steps[0].tool in {"open_path", "open_application"}:
        return steps
    return None


def _clause_to_intent(clause: str, *, target: str, session_id: str) -> Optional[ParsedIntent]:
    quoted = clause.replace("'", "").replace('"', "")
    match = _IN_EDITOR.match(quoted)
    if match:
        name = _clean_name(match.group("name"))
        app = resolve_application_alias(match.group("app"))
        return _open_path(name, app, target, session_id)
    match = _PROJECT.match(quoted)
    if match:
        name = _clean_name(match.group("name"))
        app = resolve_application_alias(match.group("app") or "Visual Studio Code")
        return _open_path(name, app, target, session_id)
    match = _OPEN.match(quoted)
    if match is None:
        return None
    name = _clean_name(match.group("name"))
    app = canonical_application_name(name)
    return ParsedIntent(
        type="tool_call",
        message=f"Opening {app}.",
        spoken_reply=f"Opening {app}.",
        session_id=session_id,
        tool="open_application",
        target=target,  # type: ignore[arg-type]
        arguments={"application": app},
        risk="low",
        requires_confirmation=False,
    )


def _open_url_intent(url: str, spoken: str, target: str, session_id: str) -> ParsedIntent:
    return ParsedIntent(
        type="tool_call",
        message=spoken,
        spoken_reply=spoken,
        session_id=session_id,
        tool="open_url",
        target=target,  # type: ignore[arg-type]
        arguments={"url": url},
        risk="low",
        requires_confirmation=False,
    )


def _open_path(path: str, application: str, target: str, session_id: str) -> Optional[ParsedIntent]:
    if not path:
        return None
    spoken = f"Opening {path} in {application}."
    return ParsedIntent(
        type="tool_call",
        message=spoken,
        spoken_reply=spoken,
        session_id=session_id,
        tool="open_path",
        target=target,  # type: ignore[arg-type]
        arguments={"path": path, "application": application},
        risk="low",
        requires_confirmation=False,
    )


def _clean_name(value: str) -> str:
    cleaned = " ".join((value or "").strip().split())
    cleaned = re.sub(r"^(?:the|my)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .")
