"""Expand tool arguments from stored preferences and aliases before safety."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from server.ai.intent import ParsedIntent
from server.memory.keys import PATH_TOOLS, PROJECT_PARENT_TOOLS
from server.memory.store import MemoryStore
from server.tools.catalog import canonical_application_name, resolve_application_alias


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
    elif intent.tool == "open_path":
        app = arguments.get("application")
        path = arguments.get("path", "that folder")
        spoken = f"Opening {path} in {app}." if app else f"Opening {path}."
    elif intent.tool == "create_project":
        spoken = f"Creating {arguments.get('kind', 'node')} project {arguments.get('name')}."
    elif intent.tool in PATH_TOOLS and "path" in arguments:
        spoken = intent.spoken_reply.replace(str(intent.arguments.get("path") or ""), str(arguments["path"]), 1)
    return replace(intent, arguments=arguments, message=spoken, spoken_reply=spoken)


def enrich_arguments(tool: str, arguments: dict[str, Any], memory: MemoryStore) -> dict[str, Any]:
    updated = dict(arguments)
    if tool == "open_application":
        raw = str(updated.get("application") or "")
        resolved = memory.resolve_application(raw) or canonical_application_name(raw)
        if resolved:
            updated["application"] = resolved
    if tool == "open_path":
        raw_app = updated.get("application")
        if isinstance(raw_app, str) and raw_app.strip():
            updated["application"] = memory.resolve_application(raw_app) or resolve_application_alias(raw_app)
    if tool == "create_project":
        from server.tools.catalog import slugify_project_name

        name = slugify_project_name(str(updated.get("name") or "app"))
        updated["name"] = name
        if not str(updated.get("path") or "").strip():
            updated["path"] = name
        raw_app = updated.get("open_in")
        if isinstance(raw_app, str) and raw_app.strip():
            updated["open_in"] = memory.resolve_application(raw_app) or resolve_application_alias(raw_app)
    if tool in PATH_TOOLS and "path" in updated:
        updated["path"] = memory.resolve_path(
            str(updated["path"]),
            join_projects=tool in PROJECT_PARENT_TOOLS,
        )
    return updated
