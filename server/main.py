from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from server import __version__
from server.api.health import router as health_router
from server.api.intent import router as intent_router
from server.api.mac import router as mac_router
from server.api.memory import router as memory_router
from server.api.routes import router as chat_router
from server.api.speech import router as speech_router
from server.api.tts import router as tts_router
from server.ai.llm import LLMError
from server.ai.stt import STTError
from server.ai.tts import TTSError
from server.config import get_settings
from server.dependencies import (
    get_llm_engine,
    get_memory_store,
    get_stt_engine,
    get_tool_registry,
    get_tts_engine,
)
from server.utils.logger import get_logger, setup_logging

logger = get_logger("jarvis.server")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)
    llm = get_llm_engine()
    stt = get_stt_engine()
    tts = get_tts_engine()
    registry = get_tool_registry()
    memory = get_memory_store()
    logger.info(
        "Jarvis Phase 8 starting host=%s port=%s llm=%s stt=%s tts=%s tools=%s memory=%s",
        settings.jarvis_host,
        settings.jarvis_port,
        settings.model_file,
        settings.stt_model_file,
        settings.tts_model_file,
        len(registry),
        memory.path,
    )
    if settings.llm_preload:
        try:
            llm.load()
        except LLMError as exc:
            logger.error("LLM preload failed: %s", exc)
    if settings.stt_preload:
        try:
            stt.load()
        except STTError as exc:
            logger.error("STT preload failed: %s", exc)
    if settings.tts_preload:
        try:
            tts.load()
        except TTSError as exc:
            logger.error("TTS preload failed: %s", exc)
    yield
    llm.shutdown()
    stt.shutdown()
    tts.shutdown()
    try:
        get_memory_store().close()
    except Exception:
        pass
    logger.info("Jarvis stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Jarvis",
        description="Local offline personal assistant brain (Phase 8: LLM + STT + TTS + intent + safety + tools + Mac client + memory)",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    application.include_router(health_router)
    application.include_router(chat_router)
    application.include_router(speech_router)
    application.include_router(tts_router)
    application.include_router(intent_router)
    application.include_router(mac_router)
    application.include_router(memory_router)

    @application.exception_handler(LLMError)
    async def llm_error_handler(_request, exc: LLMError) -> JSONResponse:
        logger.exception("Unhandled LLM error")
        return JSONResponse(
            status_code=503,
            content={"type": "error", "error": "llm_unavailable", "detail": str(exc)},
        )

    @application.exception_handler(STTError)
    async def stt_error_handler(_request, exc: STTError) -> JSONResponse:
        logger.exception("Unhandled STT error")
        return JSONResponse(
            status_code=503,
            content={"type": "error", "error": "stt_unavailable", "detail": str(exc)},
        )

    @application.exception_handler(TTSError)
    async def tts_error_handler(_request, exc: TTSError) -> JSONResponse:
        logger.exception("Unhandled TTS error")
        return JSONResponse(
            status_code=503,
            content={"type": "error", "error": "tts_unavailable", "detail": str(exc)},
        )

    return application


app = create_app()
