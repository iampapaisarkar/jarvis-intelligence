from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from server.ai.intent import IntentParser
from server.api.schemas import (
    ConfirmRequest,
    IntentRequest,
    IntentResponse,
    PendingQueryResponse,
    TokenUsage,
    ToolListItem,
    ToolListResponse,
)
from server.config import Settings, get_settings
from server.dependencies import (
    get_confirmation_store,
    get_intent_parser,
    get_safety_engine,
    get_tool_executor,
    get_tool_registry,
)
from server.safety.confirm import ConfirmationStore
from server.safety.engine import GatedIntent, SafetyEngine
from server.safety.phrases import classify_confirmation
from server.tools.executor import LocalToolExecutor, apply_execution, detect_backend
from server.tools.registry import ToolRegistry
from server.utils.logger import get_logger
from server.utils.security import verify_auth_token

router = APIRouter(tags=["intent"])
logger = get_logger("jarvis.intent.api")


def _response(gated: GatedIntent) -> IntentResponse:
    return IntentResponse(
        type=gated.type,
        executed=gated.executed,
        confirmed=gated.confirmed,
        safety=gated.safety,
        message=gated.message,
        spoken_reply=gated.spoken_reply,
        session_id=gated.session_id,
        tool=gated.tool,
        target=gated.target,
        arguments=gated.arguments_or_empty,
        risk=gated.risk,  # type: ignore[arg-type]
        requires_confirmation=gated.requires_confirmation,
        confirmation_id=gated.confirmation_id,
        reason=gated.reason,
        model=gated.model,
        usage=TokenUsage(
            prompt_tokens=gated.prompt_tokens,
            completion_tokens=gated.completion_tokens,
            total_tokens=gated.total_tokens,
        ),
        latency_ms=gated.latency_ms,
        parse_recovered=gated.parse_recovered,
        result=gated.result,
    )


def _cancelled(session_id: str, message: str) -> IntentResponse:
    return IntentResponse(
        type="reply",
        executed=False,
        safety="not_applicable",
        message=message,
        spoken_reply=message,
        session_id=session_id,
        reason="cancelled",
        usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


@router.get(
    "/v1/tools",
    response_model=ToolListResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def list_tools(
    registry: ToolRegistry = Depends(get_tool_registry),
    settings: Settings = Depends(get_settings),
) -> ToolListResponse:
    items = []
    for spec in registry.list():
        entry = spec.prompt_entry()
        items.append(
            ToolListItem(
                name=spec.name,
                description=spec.description,
                targets=list(spec.allowed_targets),
                risk=spec.risk,
                requires_confirmation=spec.requires_confirmation,
                arguments=entry["arguments"],
                required=entry["required"],
            )
        )
    backend = detect_backend(settings)
    execution = "disabled" if backend == "off" else backend
    return ToolListResponse(execution=execution, tools=items)


@router.get(
    "/v1/pending",
    response_model=PendingQueryResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def pending_action(
    session_id: str = Query(min_length=1, max_length=128),
    store: ConfirmationStore = Depends(get_confirmation_store),
) -> PendingQueryResponse:
    pending = store.get_for_session(session_id)
    if pending is None:
        return PendingQueryResponse(pending=False, session_id=session_id)
    return PendingQueryResponse(
        pending=True,
        session_id=session_id,
        confirmation_id=pending.confirmation_id,
        tool=pending.tool,
        target=pending.target,
        arguments=pending.arguments,
        risk=pending.risk,
        spoken_reply=pending.spoken_summary,
        expires_in_seconds=round(max(0.0, pending.expires_at - time.time()), 1),
    )


@router.post(
    "/v1/confirm",
    response_model=IntentResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def confirm_action(
    body: ConfirmRequest,
    store: ConfirmationStore = Depends(get_confirmation_store),
    engine: SafetyEngine = Depends(get_safety_engine),
    registry: ToolRegistry = Depends(get_tool_registry),
    executor: LocalToolExecutor = Depends(get_tool_executor),
) -> IntentResponse:
    pending = store.get(body.session_id, body.confirmation_id)
    if pending is None:
        other = store.get_for_session(body.session_id)
        if other is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Confirmation does not match this session.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending confirmation for this session.",
        )
    if not body.approved:
        store.cancel_session(body.session_id)
        logger.info("confirmation rejected", extra={"session_id": body.session_id})
        return _cancelled(body.session_id, "Cancelled.")
    popped = store.pop(body.session_id, body.confirmation_id)
    if popped is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="That confirmation expired. Please ask again.",
        )
    return _response(apply_execution(engine.approve(popped, session_id=body.session_id), registry=registry, executor=executor))


@router.post(
    "/v1/intent",
    response_model=IntentResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def parse_intent(
    body: IntentRequest,
    parser: IntentParser = Depends(get_intent_parser),
    engine: SafetyEngine = Depends(get_safety_engine),
    store: ConfirmationStore = Depends(get_confirmation_store),
    registry: ToolRegistry = Depends(get_tool_registry),
    executor: LocalToolExecutor = Depends(get_tool_executor),
) -> IntentResponse:
    session_id = body.session_id or str(uuid.uuid4())
    logger.info(
        "intent request chars=%s target=%s",
        len(body.text),
        body.target,
        extra={"session_id": session_id},
    )
    handled = _handle_spoken_confirmation(body.text, session_id, store, engine, registry, executor)
    if handled is not None:
        return handled

    parsed = await parser.parse(
        body.text,
        session_id=session_id,
        default_target=body.target,
    )
    return _response(apply_execution(engine.gate(parsed), registry=registry, executor=executor))


def _handle_spoken_confirmation(
    text: str,
    session_id: str,
    store: ConfirmationStore,
    engine: SafetyEngine,
    registry: ToolRegistry,
    executor: LocalToolExecutor,
) -> IntentResponse | None:
    verdict = classify_confirmation(text)
    pending = store.get_for_session(session_id)
    if verdict == "yes":
        if pending is None:
            return _cancelled(session_id, "There is nothing waiting for confirmation.")
        popped = store.pop(session_id, pending.confirmation_id)
        if popped is None:
            return _cancelled(session_id, "That confirmation expired. Please ask again.")
        return _response(apply_execution(engine.approve(popped, session_id=session_id), registry=registry, executor=executor))
    if verdict == "no":
        if pending is not None:
            store.cancel_session(session_id)
        return _cancelled(session_id, "Cancelled.")
    if pending is not None:
        store.cancel_session(session_id)
        logger.info(
            "pending confirmation replaced by new request",
            extra={"session_id": session_id},
        )
    return None
