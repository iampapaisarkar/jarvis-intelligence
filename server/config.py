from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
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

    llm_model_path: Path = Path("models/llm/qwen2.5-1.5b-instruct-q4_k_m.gguf")
    llm_chat_format: str = "chatml"
    llm_n_ctx: int = 2048
    llm_n_threads: Optional[int] = None
    llm_n_gpu_layers: int = 0
    llm_n_batch: int = 256
    llm_max_tokens: int = 256
    llm_temperature: float = 0.7
    llm_preload: bool = False

    stt_model_path: Path = Path("models/stt")
    tts_model_path: Path = Path("models/tts")

    log_level: str = "INFO"
    log_dir: Path = Path("logs")

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

    def resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (REPO_ROOT / path).resolve()

    @property
    def model_file(self) -> Path:
        return self.resolve_path(self.llm_model_path)

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
