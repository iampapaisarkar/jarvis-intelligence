"""Turn user text into a validated intent. Never executes tools."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from server.ai.llm import ChatTurn, LLMEngine, LLMResult
from server.ai.prompts import build_intent_system_prompt
from server.config import Settings
from server.tools.base import Target, ToolSpec, ToolValidationError, UnknownToolError
from server.tools.registry import ToolRegistry
from server.utils.logger import get_logger

logger = get_logger("jarvis.intent")

IntentType = Literal["tool_call", "clarification", "reply"]
_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_RETRY_HINT = (
    "Your previous reply was not valid JSON for Jarvis. "
    "Reply with one JSON object only, no markdown."
)


class IntentError(Exception):
    pass


class IntentParseError(IntentError):
    pass


@dataclass(frozen=True)
class ParsedIntent:
    type: IntentType
    message: str
    spoken_reply: str
    session_id: str
    executed: bool = False
    tool: Optional[str] = None
    target: Optional[Target] = None
    arguments: dict[str, Any] = field(default_factory=dict)
    risk: Optional[str] = None
    requires_confirmation: Optional[bool] = None
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: Optional[str] = None
    parse_recovered: bool = False


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = (text or "").strip()
    if not stripped:
        raise IntentParseError("empty model output")
    fenced = _FENCE.search(stripped)
    candidate = fenced.group(1).strip() if fenced else stripped
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        raise IntentParseError("no JSON object in model output")
    blob = candidate[start : end + 1]
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise IntentParseError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise IntentParseError("JSON root must be an object")
    return data


def _spoken(data: dict[str, Any], fallback: str) -> str:
    for key in ("spoken_reply", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


class IntentParser:
    def __init__(
        self,
        engine: LLMEngine,
        registry: ToolRegistry,
        settings: Settings,
    ) -> None:
        self._engine = engine
        self._registry = registry
        self._settings = settings
        catalog = [spec.prompt_entry() for spec in registry.list()]
        self._system_prompt = build_intent_system_prompt(
            catalog, settings.jarvis_default_target
        )

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    async def parse(
        self,
        text: str,
        *,
        session_id: str,
        default_target: Optional[str] = None,
        memory_context: str = "",
    ) -> ParsedIntent:
        user_text = text.strip()
        if not user_text:
            return self._clarification(
                "What would you like me to do?",
                session_id=session_id,
                recovered=False,
            )

        messages = [
            ChatTurn(role="system", content=self._system_prompt),
            ChatTurn(role="user", content=user_text),
        ]
        if memory_context:
            messages.insert(1, ChatTurn(role="system", content=memory_context))
        result, recovered = await self._complete(messages, session_id)
        try:
            data = extract_json_object(result.text)
            return self._build(data, result, session_id, override_target=default_target, recovered=recovered)
        except (IntentParseError, ToolValidationError, UnknownToolError) as exc:
            logger.info(
                "intent fallback clarification reason=%s",
                exc,
                extra={"session_id": session_id},
            )
            return self._clarification(
                "I did not catch a clear action. Please say that again, a bit more specifically.",
                session_id=session_id,
                result=result,
                recovered=True,
            )

    async def _complete(
        self,
        messages: list[ChatTurn],
        session_id: str,
    ) -> tuple[LLMResult, bool]:
        recovered = False
        result = await self._engine.chat(
            messages,
            max_tokens=self._settings.intent_max_tokens,
            temperature=self._settings.intent_temperature,
            session_id=session_id,
            json_mode=True,
        )
        if self._looks_like_json(result.text):
            return result, recovered
        retries = max(0, self._settings.intent_json_retries)
        if retries < 1:
            return result, recovered
        recovered = True
        retry_messages = list(messages)
        retry_messages.append(ChatTurn(role="assistant", content=result.text or " "))
        retry_messages.append(ChatTurn(role="user", content=_RETRY_HINT))
        retry = await self._engine.chat(
            retry_messages,
            max_tokens=self._settings.intent_max_tokens,
            temperature=self._settings.intent_temperature,
            session_id=session_id,
            json_mode=True,
        )
        combined = LLMResult(
            text=retry.text,
            model_path=retry.model_path,
            prompt_tokens=retry.prompt_tokens + result.prompt_tokens,
            completion_tokens=retry.completion_tokens + result.completion_tokens,
            total_tokens=retry.total_tokens + result.total_tokens,
            latency_ms=round(retry.latency_ms + result.latency_ms, 1),
            finish_reason=retry.finish_reason,
        )
        return combined, recovered

    @staticmethod
    def _looks_like_json(text: str) -> bool:
        try:
            extract_json_object(text)
            return True
        except IntentParseError:
            return False

    def _build(
        self,
        data: dict[str, Any],
        result: LLMResult,
        session_id: str,
        override_target: Optional[str],
        recovered: bool,
    ) -> ParsedIntent:
        kind = str(data.get("type") or "").strip().lower()
        if kind == "clarification":
            message = _spoken(data, "Could you clarify that request?")
            return self._attach_usage(
                ParsedIntent(
                    type="clarification",
                    message=message,
                    spoken_reply=_spoken(data, message),
                    session_id=session_id,
                    parse_recovered=recovered,
                ),
                result,
            )
        if kind == "reply":
            message = _spoken(data, "How can I help you?")
            return self._attach_usage(
                ParsedIntent(
                    type="reply",
                    message=message,
                    spoken_reply=_spoken(data, message),
                    session_id=session_id,
                    parse_recovered=recovered,
                ),
                result,
            )
        if kind != "tool_call":
            raise IntentParseError(f"unsupported intent type: {kind or 'missing'}")

        tool_name = str(data.get("tool") or "").strip()
        spec = self._registry.require(tool_name)
        arguments = spec.validate_args(data.get("arguments"))
        requested = data.get("target")
        fallback = self._settings.jarvis_default_target
        if isinstance(override_target, str) and override_target in spec.allowed_targets:
            target = spec.resolve_target(override_target, fallback)
        else:
            target = spec.resolve_target(
                requested if isinstance(requested, str) else None,
                fallback if fallback in spec.allowed_targets else spec.allowed_targets[0],
            )
        spoken = _spoken(data, _default_spoken(spec, arguments, target))
        logger.info(
            "intent tool=%s target=%s risk=%s executed=false",
            spec.name,
            target,
            spec.risk,
            extra={"session_id": session_id},
        )
        return self._attach_usage(
            ParsedIntent(
                type="tool_call",
                message=spoken,
                spoken_reply=spoken,
                session_id=session_id,
                tool=spec.name,
                target=target,
                arguments=arguments,
                risk=spec.risk,
                requires_confirmation=spec.requires_confirmation,
                parse_recovered=recovered,
            ),
            result,
        )

    def _clarification(
        self,
        message: str,
        *,
        session_id: str,
        result: Optional[LLMResult] = None,
        recovered: bool,
    ) -> ParsedIntent:
        intent = ParsedIntent(
            type="clarification",
            message=message,
            spoken_reply=message,
            session_id=session_id,
            parse_recovered=recovered,
        )
        if result is None:
            return intent
        return self._attach_usage(intent, result)

    @staticmethod
    def _attach_usage(intent: ParsedIntent, result: LLMResult) -> ParsedIntent:
        return ParsedIntent(
            type=intent.type,
            message=intent.message,
            spoken_reply=intent.spoken_reply,
            session_id=intent.session_id,
            executed=False,
            tool=intent.tool,
            target=intent.target,
            arguments=intent.arguments,
            risk=intent.risk,
            requires_confirmation=intent.requires_confirmation,
            model=result.model_path,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            latency_ms=result.latency_ms,
            finish_reason=result.finish_reason,
            parse_recovered=intent.parse_recovered,
        )


def _default_spoken(spec: ToolSpec, arguments: dict[str, Any], target: str) -> str:
    if spec.name == "open_application":
        return f"Opening {arguments.get('application', 'the application')}."
    if spec.name == "list_directory":
        return f"Listing {arguments.get('path', 'that folder')}."
    if spec.name == "create_folder":
        return f"I can create {arguments.get('path', 'that folder')} on {target} after confirmation."
    if spec.name == "create_file":
        return f"I can create {arguments.get('path', 'that file')} on {target} after confirmation."
    if spec.name == "get_system_info":
        return f"I'll check system info on {target}."
    if spec.name == "remember_preference":
        return f"I'll remember {arguments.get('key')}."
    return f"Planning {spec.name}."
