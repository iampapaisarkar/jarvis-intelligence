from fastapi import APIRouter, Depends

from server import __version__
from server.ai.llm import LLMEngine
from server.ai.stt import SpeechToText
from server.api.schemas import HealthResponse, LlmHealth, ModelHealth
from server.config import Settings, get_settings
from server.dependencies import get_llm_engine, get_stt_engine

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_settings),
    llm: LLMEngine = Depends(get_llm_engine),
    stt: SpeechToText = Depends(get_stt_engine),
) -> HealthResponse:
    llm_present = llm.model_file_present()
    stt_present = stt.model_file_present()
    return HealthResponse(
        status="ok" if llm_present else "degraded",
        version=__version__,
        voice_ready=llm_present and stt_present,
        llm=LlmHealth(
            backend=llm.backend_name,
            model_path=llm.model_path,
            model_file_present=llm_present,
            model_loaded=llm.loaded,
            n_ctx=settings.llm_n_ctx,
            n_gpu_layers=settings.llm_n_gpu_layers,
        ),
        stt=ModelHealth(
            backend=stt.backend_name,
            model_path=stt.model_path,
            model_file_present=stt_present,
            model_loaded=stt.loaded,
        ),
    )
