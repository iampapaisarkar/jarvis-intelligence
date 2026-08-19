from fastapi import APIRouter, Depends

from server import __version__
from server.ai.llm import LLMEngine
from server.api.schemas import HealthResponse
from server.config import Settings, get_settings
from server.dependencies import get_llm_engine

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    settings: Settings = Depends(get_settings),
    engine: LLMEngine = Depends(get_llm_engine),
) -> HealthResponse:
    present = engine.model_file_present()
    return HealthResponse(
        status="ok" if present else "degraded",
        version=__version__,
        backend=engine.backend_name,
        model_path=engine.model_path,
        model_file_present=present,
        model_loaded=engine.loaded,
        n_ctx=settings.llm_n_ctx,
        n_gpu_layers=settings.llm_n_gpu_layers,
    )
