from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment-driven configuration. Paths may be relative to the repo root."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    jarvis_host: str = "0.0.0.0"
    jarvis_port: int = 8765
    jarvis_auth_token: str = "change-me"
    jarvis_default_target: str = "windows"

    llm_model_path: Path = Path("models/llm/qwen2.5-1.5b-instruct-q4_k_m.gguf")
    llm_chat_format: str = "chatml"
    llm_n_ctx: int = 2048
    llm_n_threads: Optional[int] = None
    llm_n_gpu_layers: int = 0
    llm_n_batch: int = 256
    llm_max_tokens: int = 256
    llm_temperature: float = 0.7
    llm_preload: bool = False

    stt_model_path: Path = Path("models/stt/ggml-base.bin")
    stt_language: str = "auto"
    stt_n_threads: Optional[int] = None
    stt_preload: bool = False
    stt_use_gpu: bool = False
    stt_max_audio_seconds: float = 20.0
    stt_max_upload_bytes: int = 8 * 1024 * 1024
    mic_sample_rate: int = 16000
    tts_model_path: Path = Path("models/tts/en_US-lessac-low.onnx")
    tts_bn_model_path: Optional[Path] = None
    tts_preload: bool = False
    tts_use_cuda: bool = False
    tts_max_chars: int = 500

    intent_max_tokens: int = 192
    intent_temperature: float = 0.1
    intent_json_retries: int = 1

    safety_confirmation_ttl_seconds: int = 120

    jarvis_tools_enabled: bool = True
    jarvis_tools_backend: str = "auto"
    jarvis_workspace: Optional[Path] = None
    jarvis_terminal_timeout_seconds: int = 10
    jarvis_mac_timeout_seconds: int = 20
    jarvis_memory_path: Path = Path("data/jarvis.sqlite")
    jarvis_memory_history_limit: int = 200
    jarvis_wake_enabled: bool = True
    jarvis_wake_word: str = "jarvis"

    log_level: str = "INFO"
    log_dir: Path = Path("logs")

    @field_validator("jarvis_default_target")
    @classmethod
    def _default_target(cls, value: str) -> str:
        lower = value.strip().lower()
        if lower not in {"windows", "mac"}:
            raise ValueError("JARVIS_DEFAULT_TARGET must be windows or mac")
        return lower

    @field_validator("llm_n_ctx")
    @classmethod
    def _ctx_window(cls, value: int) -> int:
        if value < 256 or value > 8192:
            raise ValueError("LLM_N_CTX must be between 256 and 8192 for the 8 GB CPU target")
        return value

    @field_validator("llm_max_tokens")
    @classmethod
    def _max_tokens(cls, value: int) -> int:
        if value < 1 or value > 2048:
            raise ValueError("LLM_MAX_TOKENS must be between 1 and 2048")
        return value

    @field_validator("log_level")
    @classmethod
    def _log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return upper

    @field_validator("stt_max_audio_seconds")
    @classmethod
    def _stt_seconds(cls, value: float) -> float:
        if value < 1 or value > 60:
            raise ValueError("STT_MAX_AUDIO_SECONDS must be between 1 and 60")
        return value

    @field_validator("tts_max_chars")
    @classmethod
    def _tts_chars(cls, value: int) -> int:
        if value < 1 or value > 2000:
            raise ValueError("TTS_MAX_CHARS must be between 1 and 2000")
        return value

    @field_validator("intent_max_tokens")
    @classmethod
    def _intent_tokens(cls, value: int) -> int:
        if value < 32 or value > 512:
            raise ValueError("INTENT_MAX_TOKENS must be between 32 and 512")
        return value

    @field_validator("intent_json_retries")
    @classmethod
    def _intent_retries(cls, value: int) -> int:
        if value < 0 or value > 2:
            raise ValueError("INTENT_JSON_RETRIES must be between 0 and 2")
        return value

    @field_validator("safety_confirmation_ttl_seconds")
    @classmethod
    def _confirm_ttl(cls, value: int) -> int:
        if value < 15 or value > 3600:
            raise ValueError("SAFETY_CONFIRMATION_TTL_SECONDS must be between 15 and 3600")
        return value

    @field_validator("jarvis_tools_backend")
    @classmethod
    def _tools_backend(cls, value: str) -> str:
        lower = value.strip().lower()
        if lower not in {"auto", "windows", "posix", "off", "disabled"}:
            raise ValueError("JARVIS_TOOLS_BACKEND must be auto, windows, posix, or off")
        return lower

    @field_validator("jarvis_terminal_timeout_seconds")
    @classmethod
    def _term_timeout(cls, value: int) -> int:
        if value < 1 or value > 60:
            raise ValueError("JARVIS_TERMINAL_TIMEOUT_SECONDS must be between 1 and 60")
        return value

    @field_validator("jarvis_mac_timeout_seconds")
    @classmethod
    def _mac_timeout(cls, value: int) -> int:
        if value < 3 or value > 120:
            raise ValueError("JARVIS_MAC_TIMEOUT_SECONDS must be between 3 and 120")
        return value

    @field_validator("jarvis_memory_history_limit")
    @classmethod
    def _memory_history(cls, value: int) -> int:
        if value < 20 or value > 2000:
            raise ValueError("JARVIS_MEMORY_HISTORY_LIMIT must be between 20 and 2000")
        return value

    @field_validator("jarvis_wake_word")
    @classmethod
    def _wake_word(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2 or len(cleaned) > 32:
            raise ValueError("JARVIS_WAKE_WORD must be between 2 and 32 characters")
        return cleaned

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (REPO_ROOT / path).resolve()

    @property
    def model_file(self) -> Path:
        return self.resolve_path(self.llm_model_path)

    @property
    def stt_model_file(self) -> Path:
        path = self.resolve_path(self.stt_model_path)
        if path.is_file():
            return path
        if path.is_dir():
            preferred = (
                "ggml-base.bin",
                "ggml-base-q5_1.bin",
                "ggml-small.bin",
                "ggml-tiny.bin",
            )
            for name in preferred:
                candidate = path / name
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return candidate
            matches = sorted(
                p for p in path.glob("ggml-*.bin") if p.is_file() and p.stat().st_size > 0
            )
            if matches:
                return matches[0]
        return path

    @property
    def tts_model_file(self) -> Path:
        path = self.resolve_path(self.tts_model_path)
        if path.is_file():
            return path
        if path.is_dir():
            preferred = (
                "en_US-lessac-low.onnx",
                "en_US-lessac-medium.onnx",
                "en_US-amy-low.onnx",
            )
            for name in preferred:
                candidate = path / name
                if candidate.is_file() and candidate.stat().st_size > 0:
                    return candidate
            matches = sorted(
                p for p in path.glob("*.onnx") if p.is_file() and p.stat().st_size > 0
            )
            if matches:
                return matches[0]
        return path

    @property
    def memory_file(self) -> Path:
        return self.resolve_path(self.jarvis_memory_path)

    @property
    def log_directory(self) -> Path:
        return self.resolve_path(self.log_dir)

    @property
    def auth_required(self) -> bool:
        return bool(self.jarvis_auth_token.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
