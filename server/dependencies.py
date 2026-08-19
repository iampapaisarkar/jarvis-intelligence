from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from server.ai.intent import IntentParser
from server.ai.llm import LLMEngine, LlamaCppEngine
from server.ai.stt import SpeechToText, WhisperCppSTT
from server.ai.tts import PiperTTS, TextToSpeech
from server.config import Settings, get_settings
from server.safety.confirm import ConfirmationStore
from server.safety.engine import SafetyEngine
from server.mac.bridge import MacBridge
from server.memory.keys import OWNER_SETTING_MAP
from server.memory.store import MemoryStore
from server.tools.catalog import default_registry
from server.tools.executor import LocalToolExecutor
from server.tools.registry import ToolRegistry


@lru_cache
def get_llm_engine() -> LlamaCppEngine:
    """Process-wide singleton. Do not construct a second llama.cpp instance."""
    return LlamaCppEngine(get_settings())


@lru_cache
def get_stt_engine() -> WhisperCppSTT:
    """Process-wide singleton. Do not construct a second whisper.cpp instance."""
    return WhisperCppSTT(get_settings())


@lru_cache
def get_tts_engine() -> PiperTTS:
    """Process-wide singleton. Do not construct a second Piper instance."""
    return PiperTTS(get_settings())


@lru_cache
def get_tool_registry() -> ToolRegistry:
    return default_registry()


@lru_cache
def get_confirmation_store() -> ConfirmationStore:
    return ConfirmationStore(ttl_seconds=get_settings().safety_confirmation_ttl_seconds)


@lru_cache
def get_mac_bridge() -> MacBridge:
    return MacBridge(timeout_seconds=get_settings().jarvis_mac_timeout_seconds)


@lru_cache
def get_memory_store() -> MemoryStore:
    settings = get_settings()
    store = MemoryStore(settings.memory_file, history_limit=settings.jarvis_memory_history_limit)
    store.seed_from_values(
        {memory_key: str(getattr(settings, setting, "") or "") for setting, memory_key in OWNER_SETTING_MAP}
    )
    return store


def get_tool_executor(settings: Settings = Depends(get_settings)) -> LocalToolExecutor:
    return LocalToolExecutor(settings)


def get_safety_engine(
    registry: ToolRegistry = Depends(get_tool_registry),
    store: ConfirmationStore = Depends(get_confirmation_store),
) -> SafetyEngine:
    return SafetyEngine(registry, store)


def get_intent_parser(
    engine: LLMEngine = Depends(get_llm_engine),
    registry: ToolRegistry = Depends(get_tool_registry),
    settings: Settings = Depends(get_settings),
) -> IntentParser:
    return IntentParser(engine, registry, settings)


def llm_engine_dep(engine: LLMEngine = Depends(get_llm_engine)) -> LLMEngine:
    return engine


def stt_engine_dep(engine: SpeechToText = Depends(get_stt_engine)) -> SpeechToText:
    return engine


def tts_engine_dep(engine: TextToSpeech = Depends(get_tts_engine)) -> TextToSpeech:
    return engine


def settings_dep(settings: Settings = Depends(get_settings)) -> Settings:
    return settings


def reset_singletons() -> None:
    try:
        get_confirmation_store().clear()
    except Exception:
        pass
    try:
        if get_memory_store.cache_info().currsize > 0:
            get_memory_store().close()
    except Exception:
        pass
    get_llm_engine.cache_clear()
    get_stt_engine.cache_clear()
    get_tts_engine.cache_clear()
    get_tool_registry.cache_clear()
    get_confirmation_store.cache_clear()
    get_mac_bridge.cache_clear()
    get_memory_store.cache_clear()
    get_settings.cache_clear()
