"""Local GGUF inference via llama.cpp. Replaceable backend; no cloud APIs."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from server.ai.prompts import JARVIS_SYSTEM_PROMPT
from server.config import Settings
from server.utils.logger import get_logger

logger = get_logger("jarvis.llm")


class LLMError(Exception):
    """Raised when the local model cannot be used."""


class ModelNotFoundError(LLMError):
    pass


class ModelLoadError(LLMError):
    pass


@dataclass(frozen=True)
class ChatTurn:
    role: str
    content: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    model_path: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    finish_reason: Optional[str] = None


class LLMEngine(Protocol):
    """Abstract local LLM. Later phases depend on this, not llama.cpp details."""

    @property
    def loaded(self) -> bool: ...

    @property
    def model_path(self) -> str: ...

    @property
    def backend_name(self) -> str: ...

    def model_file_present(self) -> bool: ...

    def load(self) -> None: ...

    def unload(self) -> None: ...

    def shutdown(self) -> None: ...

    async def chat(
        self,
        messages: list[ChatTurn],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        session_id: str = "-",
    ) -> LLMResult: ...


def _default_thread_count() -> int:
    cpu = os.cpu_count() or 4
    # Leave headroom for the OS and FastAPI on an 8 GB i3-class machine.
    return max(1, min(4, cpu - 1 if cpu > 2 else cpu))


class LlamaCppEngine:
    """Single-process, single-worker llama.cpp wrapper. Lazy-loads the GGUF."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._llama: Any = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-llm")

    @property
    def backend_name(self) -> str:
        return "llama.cpp"

    @property
    def loaded(self) -> bool:
        return self._llama is not None

    @property
    def model_path(self) -> str:
        return str(self._settings.model_file)

    def model_file_present(self) -> bool:
        path = self._settings.model_file
        return path.is_file() and path.stat().st_size > 0

    def load(self) -> None:
        with self._lock:
            if self._llama is not None:
                return
            path = self._settings.model_file
            if not path.is_file():
                raise ModelNotFoundError(
                    f"GGUF model not found at {path}. "
                    "Run: python scripts/download_model.py"
                )
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                raise ModelLoadError(
                    "llama-cpp-python is not installed. "
                    "Activate the venv and run: pip install -r requirements.txt"
                ) from exc

            n_threads = self._settings.llm_n_threads or _default_thread_count()
            logger.info(
                "Loading GGUF model path=%s n_ctx=%s n_threads=%s n_gpu_layers=%s",
                path,
                self._settings.llm_n_ctx,
                n_threads,
                self._settings.llm_n_gpu_layers,
            )
            started = time.perf_counter()
            try:
                self._llama = Llama(
                    model_path=str(path),
                    n_ctx=self._settings.llm_n_ctx,
                    n_threads=n_threads,
                    n_gpu_layers=self._settings.llm_n_gpu_layers,
                    n_batch=self._settings.llm_n_batch,
                    chat_format=self._settings.llm_chat_format,
                    verbose=False,
                    use_mmap=True,
                    use_mlock=False,
                )
            except Exception as exc:  # llama.cpp raises generic errors on bad files
                self._llama = None
                raise ModelLoadError(f"Failed to load GGUF at {path}: {exc}") from exc
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("Model loaded in %.0f ms", elapsed_ms)

    def unload(self) -> None:
        with self._lock:
            self._llama = None
        logger.info("Model unloaded")

    def shutdown(self) -> None:
        self.unload()
        self._executor.shutdown(wait=False)

    def _ensure_system_prompt(self, messages: list[ChatTurn]) -> list[dict[str, str]]:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        if not payload or payload[0]["role"] != "system":
            payload.insert(0, {"role": "system", "content": JARVIS_SYSTEM_PROMPT})
        return payload

    def _generate_sync(
        self,
        messages: list[ChatTurn],
        max_tokens: Optional[int],
        temperature: Optional[float],
        session_id: str,
    ) -> LLMResult:
        self.load()
        assert self._llama is not None
        payload = self._ensure_system_prompt(messages)
        max_out = max_tokens or self._settings.llm_max_tokens
        temp = self._settings.llm_temperature if temperature is None else temperature

        extra = {"session_id": session_id}
        logger.info(
            "LLM generate messages=%s max_tokens=%s temperature=%s",
            len(payload),
            max_out,
            temp,
            extra=extra,
        )
        started = time.perf_counter()
        completion = self._llama.create_chat_completion(
            messages=payload,
            max_tokens=max_out,
            temperature=temp,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        choice = completion["choices"][0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = completion.get("usage") or {}
        result = LLMResult(
            text=text.strip(),
            model_path=self.model_path,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            latency_ms=round(latency_ms, 1),
            finish_reason=choice.get("finish_reason"),
        )
        logger.info(
            "LLM complete tokens=%s latency_ms=%s finish=%s",
            result.total_tokens,
            result.latency_ms,
            result.finish_reason,
            extra=extra,
        )
        return result

    async def chat(
        self,
        messages: list[ChatTurn],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        session_id: str = "-",
    ) -> LLMResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._generate_sync(messages, max_tokens, temperature, session_id),
        )
