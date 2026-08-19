from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from server.ai.intent import IntentParser
from server.api.schemas import (
    IntentRequest,
    IntentResponse,
    TokenUsage,
    ToolListItem,
    ToolListResponse,
)
from server.dependencies import get_intent_parser, get_tool_registry
from server.tools.registry import ToolRegistry
from server.utils.logger import get_logger
from server.utils.security import verify_auth_token

router = APIRouter(tags=["intent"])
logger = get_logger("jarvis.intent.api")


@router.get(
    "/v1/tools",
    response_model=ToolListResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def list_tools(registry: ToolRegistry = Depends(get_tool_registry)) -> ToolListResponse:
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
    return ToolListResponse(tools=items)


@router.post(
    "/v1/intent",
    response_model=IntentResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def parse_intent(
    body: IntentRequest,
    parser: IntentParser = Depends(get_intent_parser),
) -> IntentResponse:
    session_id = body.session_id or str(uuid.uuid4())
    logger.info(
        "intent request chars=%s target=%s",
        len(body.text),
        body.target,
        extra={"session_id": session_id},
    )
    parsed = await parser.parse(
        body.text,
        session_id=session_id,
        default_target=body.target,
    )
    return IntentResponse(
        type=parsed.type,
        executed=False,
        message=parsed.message,
        spoken_reply=parsed.spoken_reply,
        session_id=parsed.session_id,
        tool=parsed.tool,
        target=parsed.target,
        arguments=parsed.arguments,
        risk=parsed.risk,  # type: ignore[arg-type]
        requires_confirmation=parsed.requires_confirmation,
        model=parsed.model,
        usage=TokenUsage(
            prompt_tokens=parsed.prompt_tokens,
            completion_tokens=parsed.completion_tokens,
            total_tokens=parsed.total_tokens,
        ),
        latency_ms=parsed.latency_ms,
        parse_recovered=parsed.parse_recovered,
    )
