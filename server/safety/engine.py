"""Deterministic safety gate. The LLM cannot override these decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from server.ai.intent import ParsedIntent
from server.memory.keys import PATH_PREFERENCE_KEYS
from server.safety.confirm import ConfirmationStore, PendingAction
from server.safety.policy import (
    application_is_forbidden,
    command_is_forbidden,
    denied_spoken,
    is_ambiguous_path,
    is_system_path,
)
from server.tools.base import Target, ToolSpec
from server.tools.registry import ToolRegistry
from server.utils.logger import get_logger

logger = get_logger("jarvis.safety")

SafetyStatus = Literal["allowed", "needs_confirmation", "denied", "not_applicable"]
ResponseType = Literal["tool_call", "clarification", "reply", "confirmation_required", "denied"]


@dataclass(frozen=True)
class GatedIntent:
    type: ResponseType
    safety: SafetyStatus
    message: str
    spoken_reply: str
    session_id: str
    executed: bool = False
    confirmed: bool = False
    confirmation_id: Optional[str] = None
    tool: Optional[str] = None
    target: Optional[Target] = None
    arguments: dict[str, Any] | None = None
    risk: Optional[str] = None
    requires_confirmation: Optional[bool] = None
    reason: Optional[str] = None
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    parse_recovered: bool = False
    result: Optional[dict[str, Any]] = None

    @property
    def arguments_or_empty(self) -> dict[str, Any]:
        return self.arguments or {}


class SafetyEngine:
    def __init__(self, registry: ToolRegistry, store: ConfirmationStore) -> None:
        self._registry = registry
        self._store = store

    @property
    def store(self) -> ConfirmationStore:
        return self._store

    def review_tool(
        self,
        spec: ToolSpec,
        *,
        target: Target,
        arguments: dict[str, Any],
    ) -> tuple[SafetyStatus, str, str]:
        """Return (status, reason_code, spoken_reply)."""
        blocked = self._hard_block(spec, target, arguments)
        if blocked:
            return "denied", blocked, denied_spoken()

        if spec.risk == "high" or spec.requires_confirmation:
            spoken = _confirm_prompt(spec, target, arguments)
            return "needs_confirmation", "confirmation_required", spoken

        if spec.risk == "medium" and "path" in arguments and is_ambiguous_path(str(arguments["path"])):
            spoken = _confirm_prompt(spec, target, arguments)
            return "needs_confirmation", "confirmation_required", spoken

        return "allowed", "allowed", _allowed_spoken(spec, target, arguments)

    def gate(self, intent: ParsedIntent) -> GatedIntent:
        if intent.type != "tool_call" or not intent.tool or not intent.target:
            return _from_intent(
                intent,
                response_type=intent.type,
                safety="not_applicable",
                spoken=intent.spoken_reply,
            )

        spec = self._registry.require(intent.tool)
        status, reason, spoken = self.review_tool(
            spec, target=intent.target, arguments=intent.arguments
        )
        logger.info(
            "safety tool=%s target=%s risk=%s status=%s reason=%s",
            spec.name,
            intent.target,
            spec.risk,
            status,
            reason,
            extra={"session_id": intent.session_id},
        )
        if status == "denied":
            self._store.cancel_session(intent.session_id)
            return _from_intent(
                intent,
                response_type="denied",
                safety="denied",
                spoken=spoken,
                reason="blocked_by_policy",
                requires_confirmation=spec.requires_confirmation,
            )
        if status == "needs_confirmation":
            pending = self._store.put(
                session_id=intent.session_id,
                tool=spec.name,
                target=intent.target,
                arguments=intent.arguments,
                risk=spec.risk,
                spoken_summary=spoken,
                extra={
                    "model": intent.model,
                    "prompt_tokens": intent.prompt_tokens,
                    "completion_tokens": intent.completion_tokens,
                    "total_tokens": intent.total_tokens,
                    "latency_ms": intent.latency_ms,
                    "parse_recovered": intent.parse_recovered,
                },
            )
            return _from_intent(
                intent,
                response_type="confirmation_required",
                safety="needs_confirmation",
                spoken=spoken,
                reason="confirmation_required",
                confirmation_id=pending.confirmation_id,
                requires_confirmation=True,
            )
        self._store.cancel_session(intent.session_id)
        return _from_intent(
            intent,
            response_type="tool_call",
            safety="allowed",
            spoken=spoken,
            reason="allowed",
            requires_confirmation=False,
        )

    def approve(self, pending: PendingAction, *, session_id: str) -> GatedIntent:
        spec = self._registry.require(pending.tool)
        blocked = self._hard_block(spec, pending.target, pending.arguments)
        extra = pending.extra
        if blocked:
            logger.info(
                "safety confirm-denied tool=%s reason=%s",
                pending.tool,
                blocked,
                extra={"session_id": session_id},
            )
            return GatedIntent(
                type="denied",
                safety="denied",
                message=denied_spoken(),
                spoken_reply=denied_spoken(),
                session_id=session_id,
                tool=pending.tool,
                target=pending.target,
                arguments=pending.arguments,
                risk=pending.risk,
                requires_confirmation=True,
                reason="blocked_by_policy",
                model=str(extra.get("model") or ""),
                prompt_tokens=int(extra.get("prompt_tokens") or 0),
                completion_tokens=int(extra.get("completion_tokens") or 0),
                total_tokens=int(extra.get("total_tokens") or 0),
                latency_ms=float(extra.get("latency_ms") or 0.0),
            )
        logger.info(
            "safety confirmed tool=%s executed=false",
            pending.tool,
            extra={"session_id": session_id},
        )
        spoken = _allowed_spoken(spec, pending.target, pending.arguments)
        return GatedIntent(
            type="tool_call",
            safety="allowed",
            message=spoken,
            spoken_reply=spoken,
            session_id=session_id,
            confirmed=True,
            confirmation_id=pending.confirmation_id,
            tool=pending.tool,
            target=pending.target,
            arguments=pending.arguments,
            risk=pending.risk,
            requires_confirmation=False,
            reason="confirmed",
            model=str(extra.get("model") or ""),
            prompt_tokens=int(extra.get("prompt_tokens") or 0),
            completion_tokens=int(extra.get("completion_tokens") or 0),
            total_tokens=int(extra.get("total_tokens") or 0),
            latency_ms=float(extra.get("latency_ms") or 0.0),
            parse_recovered=bool(extra.get("parse_recovered") or False),
        )

    def _hard_block(self, spec: ToolSpec, target: Target, arguments: dict[str, Any]) -> Optional[str]:
        path = arguments.get("path")
        if isinstance(path, str) and is_system_path(path, target, destructive=spec.name != "list_directory"):
            return "blocked_system_path"

        if spec.name == "run_terminal":
            command = str(arguments.get("command") or "")
            if command_is_forbidden(command):
                return "blocked_command"

        if spec.name == "open_application":
            app = str(arguments.get("application") or "")
            if application_is_forbidden(app):
                return "blocked_executable"

        if spec.name == "open_path":
            app = str(arguments.get("application") or "")
            if app and application_is_forbidden(app):
                return "blocked_executable"

        if spec.name == "remember_preference":
            key = str(arguments.get("key") or "")
            value = str(arguments.get("value") or "")
            if key in PATH_PREFERENCE_KEYS and is_system_path(value, target, destructive=False):
                return "blocked_system_path"

        return None


def _from_intent(
    intent: ParsedIntent,
    *,
    response_type: ResponseType,
    safety: SafetyStatus,
    spoken: str,
    reason: Optional[str] = None,
    confirmation_id: Optional[str] = None,
    requires_confirmation: Optional[bool] = None,
    confirmed: bool = False,
) -> GatedIntent:
    return GatedIntent(
        type=response_type,
        safety=safety,
        message=spoken,
        spoken_reply=spoken,
        session_id=intent.session_id,
        confirmed=confirmed,
        confirmation_id=confirmation_id,
        tool=intent.tool,
        target=intent.target,
        arguments=intent.arguments,
        risk=intent.risk,
        requires_confirmation=(
            intent.requires_confirmation if requires_confirmation is None else requires_confirmation
        ),
        reason=reason,
        model=intent.model,
        prompt_tokens=intent.prompt_tokens,
        completion_tokens=intent.completion_tokens,
        total_tokens=intent.total_tokens,
        latency_ms=intent.latency_ms,
        parse_recovered=intent.parse_recovered,
        result=None,
    )


def _confirm_prompt(spec: ToolSpec, target: str, arguments: dict[str, Any]) -> str:
    if spec.name == "create_folder":
        return f"Please confirm: create folder {arguments.get('path')} on {target}."
    if spec.name == "create_file":
        return f"Please confirm: create file {arguments.get('path')} on {target}."
    if spec.name == "delete_path":
        return f"Please confirm: delete {arguments.get('path')} on {target}. This cannot be undone."
    if spec.name == "run_terminal":
        return f"Please confirm running that command on {target}."
    if spec.name == "open_application":
        return f"Please confirm: open {arguments.get('application')} on {target}."
    return f"Please confirm {spec.name} on {target}."


def _allowed_spoken(spec: ToolSpec, target: str, arguments: dict[str, Any]) -> str:
    if spec.name == "open_application":
        return f"Opening {arguments.get('application', 'the application')}."
    if spec.name == "open_path":
        app = arguments.get("application")
        path = arguments.get("path", "that folder")
        if app:
            return f"Opening {path} in {app}."
        return f"Opening {path}."
    if spec.name == "list_directory":
        return f"Listing {arguments.get('path', 'that folder')}."
    if spec.name == "get_system_info":
        return f"I'll check system info on {target}."
    if spec.name == "create_folder":
        return f"Creating {arguments.get('path')} on {target}."
    if spec.name == "create_file":
        return f"Creating {arguments.get('path')} on {target}."
    if spec.name == "delete_path":
        return f"Deleting {arguments.get('path')} on {target}."
    if spec.name == "run_terminal":
        return f"Running that command on {target}."
    if spec.name == "remember_preference":
        return f"I'll remember {arguments.get('key')}."
    return f"Planning {spec.name}."
