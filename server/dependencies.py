from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from server.ai.llm import LLMEngine, LlamaCppEngine
from server.ai.stt import SpeechToText, WhisperCppSTT
from server.config import Settings, get_settings


@lru_cache
def get_llm_engine() -> LlamaCppEngine:
    """Process-wide singleton. Do not construct a second llama.cpp instance."""
    return LlamaCppEngine(get_settings())


@lru_cache
def get_stt_engine() -> WhisperCppSTT:
    """Process-wide singleton. Do not construct a second whisper.cpp instance."""
    return WhisperCppSTT(get_settings())


def llm_engine_dep(engine: LLMEngine = Depends(get_llm_engine)) -> LLMEngine:
    return engine


def stt_engine_dep(engine: SpeechToText = Depends(get_stt_engine)) -> SpeechToText:
    return engine


def settings_dep(settings: Settings = Depends(get_settings)) -> Settings:
    return settings


def reset_singletons() -> None:
    get_llm_engine.cache_clear()
    get_stt_engine.cache_clear()
    get_settings.cache_clear()
