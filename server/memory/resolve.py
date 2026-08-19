"""Expand tool arguments from stored preferences and aliases before safety."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from server.ai.intent import ParsedIntent
from server.memory.keys import PATH_TOOLS, PROJECT_PARENT_TOOLS
from server.memory.store import MemoryStore
from server.tools.catalog import resolve_application_alias


def is_bare_name(path: str) -> bool:
    cleaned = (path or "").strip()
    if not cleaned or cleaned.startswith("~") or cleaned.startswith("/") or cleaned.startswith("\\"):
        return False
    if len(cleaned) >= 2 and cleaned[1] == ":":
        return False
    return "/" not in cleaned and "\\" not in cleaned


def enrich_intent(intent: ParsedIntent, memory: MemoryStore) -> ParsedIntent:
    if intent.type != "tool_call" or not intent.tool:
        return intent
    arguments = enrich_arguments(intent.tool, dict(intent.arguments), memory)
    if arguments == intent.arguments:
        return intent
    spoken = intent.spoken_reply
    if intent.tool == "open_application":
        spoken = f"Opening {arguments.get('application', 'the application')}."
    elif intent.tool in PATH_TOOLS and "path" in arguments:
        spoken = intent.spoken_reply.replace(str(intent.arguments.get("path") or ""), str(arguments["path"]), 1)
    return replace(intent, arguments=arguments, message=spoken, spoken_reply=spoken)


def enrich_arguments(tool: str, arguments: dict[str, Any], memory: MemoryStore) -> dict[str, Any]:
    updated = dict(arguments)
    if tool == "open_application":
        raw = str(updated.get("application") or "")
        resolved = memory.resolve_application(raw) or resolve_application_alias(raw)
        if resolved:
            updated["application"] = resolved
    if tool in PATH_TOOLS and "path" in updated:
        updated["path"] = memory.resolve_path(
            str(updated["path"]),
            join_projects=tool in PROJECT_PARENT_TOOLS,
        )
    if tool == "remember_preference":
        key = str(updated.get("key") or "").strip().lower()
        updated["key"] = key
        updated["value"] = str(updated.get("value") or "").strip()
    return updated
