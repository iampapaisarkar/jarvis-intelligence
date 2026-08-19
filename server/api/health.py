from fastapi import APIRouter, Depends

from server import __version__
from server.ai.llm import LLMEngine
from server.ai.stt import SpeechToText
from server.ai.tts import TextToSpeech
from server.api.schemas import HealthResponse, LlmHealth, ModelHealth, SafetyHealth, ToolsHealth
from server.config import Settings, get_settings
from server.dependencies import (
    get_confirmation_store,
    get_llm_engine,
    get_stt_engine,
    get_tool_registry,
    get_tts_engine,
)
from server.safety.confirm import ConfirmationStore
from server.tools.executor import detect_backend
from server.tools.registry import ToolRegistry

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_settings),
    llm: LLMEngine = Depends(get_llm_engine),
    stt: SpeechToText = Depends(get_stt_engine),
    tts: TextToSpeech = Depends(get_tts_engine),
    registry: ToolRegistry = Depends(get_tool_registry),
    store: ConfirmationStore = Depends(get_confirmation_store),
) -> HealthResponse:
    llm_present = llm.model_file_present()
    stt_present = stt.model_file_present()
    tts_present = tts.model_file_present()
    return HealthResponse(
        status="ok" if llm_present else "degraded",
        version=__version__,
        voice_ready=llm_present and stt_present and tts_present,
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
        tts=ModelHealth(
            backend=tts.backend_name,
            model_path=tts.model_path,
            model_file_present=tts_present,
            model_loaded=tts.loaded,
        ),
        tools=ToolsHealth(
            registered=len(registry),
            execution="disabled" if detect_backend(settings) == "off" else detect_backend(settings),
            pending_confirmations=store.pending_count(),
        ),
        safety=SafetyHealth(
            policy="local",
            confirmation_ttl_seconds=settings.safety_confirmation_ttl_seconds,
        ),
    )
