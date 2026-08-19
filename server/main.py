from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from server import __version__
from server.api.health import router as health_router
from server.api.routes import router as chat_router
from server.ai.llm import LLMError
from server.config import get_settings
from server.dependencies import get_llm_engine
from server.utils.logger import get_logger, setup_logging

logger = get_logger("jarvis.server")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)
    engine = get_llm_engine()
    logger.info(
        "Jarvis Phase 1 starting host=%s port=%s model=%s",
        settings.jarvis_host,
        settings.jarvis_port,
        settings.model_file,
    )
    if settings.llm_preload:
        try:
            engine.load()
        except LLMError as exc:
            logger.error("Model preload failed: %s", exc)
    yield
    engine.shutdown()
    logger.info("Jarvis stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="Jarvis",
        description="Local offline personal assistant brain (Phase 1: LLM server)",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    application.include_router(health_router)
    application.include_router(chat_router)

    @application.exception_handler(LLMError)
    async def llm_error_handler(_request, exc: LLMError) -> JSONResponse:
        logger.exception("Unhandled LLM error")
        return JSONResponse(
            status_code=503,
            content={"type": "error", "error": "llm_unavailable", "detail": str(exc)},
        )

    return application


app = create_app()
