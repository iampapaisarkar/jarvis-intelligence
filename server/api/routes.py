from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from server.ai.llm import ChatTurn, LLMEngine, LLMError, ModelLoadError, ModelNotFoundError
from server.api.schemas import ChatRequest, ChatResponse, TokenUsage
from server.dependencies import get_llm_engine
from server.utils.logger import get_logger
from server.utils.security import verify_auth_token

router = APIRouter(tags=["chat"])
logger = get_logger("jarvis.chat")


@router.post(
    "/v1/chat",
    response_model=ChatResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def chat(
    body: ChatRequest,
    engine: LLMEngine = Depends(get_llm_engine),
) -> ChatResponse:
    if body.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Streaming is not enabled in Phase 1. Set stream=false.",
        )

    session_id = body.session_id or str(uuid.uuid4())
    turns = [ChatTurn(role=m.role, content=m.content) for m in body.messages]
    logger.info(
        "chat request messages=%s",
        len(turns),
        extra={"session_id": session_id},
    )

    try:
        result = await engine.chat(
            turns,
            max_tokens=body.max_tokens,
            temperature=body.temperature,
            session_id=session_id,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ModelLoadError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LLMError as exc:
        logger.exception("LLM error", extra={"session_id": session_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local model inference failed. See server logs.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected chat failure", extra={"session_id": session_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local model inference failed. See server logs.",
        ) from exc

    if not result.text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The local model returned an empty reply.",
        )

    return ChatResponse(
        message=result.text,
        session_id=session_id,
        model=result.model_path,
        usage=TokenUsage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        ),
        latency_ms=result.latency_ms,
        finish_reason=result.finish_reason,
    )
