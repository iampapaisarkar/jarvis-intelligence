"""Deterministic multi-open plans. The small CPU model often drops the second action."""

from __future__ import annotations

import re
from typing import Optional

from server.ai.intent import ParsedIntent
from server.tools.catalog import is_known_application, resolve_application_alias

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
    if steps and steps[0].tool == "open_path":
        return steps
    if steps and steps[0].tool == "open_application" and is_known_application(
        str(steps[0].arguments.get("application") or "")
    ):
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
    if is_known_application(name):
        app = resolve_application_alias(name)
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
    return _open_path(name, "Visual Studio Code", target, session_id)


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
