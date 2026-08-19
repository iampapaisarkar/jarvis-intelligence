"""Local speech-to-text via whisper.cpp. Replaceable backend; no cloud APIs."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from server.config import Settings
from server.utils.logger import get_logger

logger = get_logger("jarvis.stt")

LANGUAGE_ALIASES = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "bn": "bn",
    "ben": "bn",
    "bangla": "bn",
    "bengali": "bn",
    "auto": None,
}


class STTError(Exception):
    """Raised when local speech recognition cannot be used."""


class STTModelNotFoundError(STTError):
    pass


class STTModelLoadError(STTError):
    pass


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    confidence: Optional[float] = None


@dataclass(frozen=True)
class Transcript:
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration_ms: float = 0.0
    latency_ms: float = 0.0
    model_path: str = ""


class SpeechToText(Protocol):
    """Abstract local STT. The rest of Jarvis must not import whisper.cpp types."""

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

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: Optional[str] = None,
        session_id: str = "-",
    ) -> Transcript: ...


def _default_thread_count() -> int:
    cpu = os.cpu_count() or 4
    return max(1, min(4, cpu - 1 if cpu > 2 else cpu))


def normalize_language(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    key = value.strip().lower()
    if not key:
        return None
    if key in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[key]
    if len(key) == 2:
        return key
    raise STTError(f"Unsupported language hint: {value}")


def _segment_times_ms(segment: Any) -> tuple[float, float]:
    t0 = getattr(segment, "t0", None)
    t1 = getattr(segment, "t1", None)
    if t0 is None:
        t0 = getattr(segment, "start", 0.0)
    if t1 is None:
        t1 = getattr(segment, "end", 0.0)
    # whisper.cpp historically stores centiseconds in t0/t1.
    start = float(t0 or 0.0)
    end = float(t1 or 0.0)
    if end <= 600 and start <= 600:
        return start * 10.0, end * 10.0
    return start, end


def _segment_confidence(segment: Any) -> Optional[float]:
    for attr in ("probability", "confidence", "p"):
        value = getattr(segment, attr, None)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number < 0:
            return max(0.0, min(1.0, pow(2.718281828, number)))
        return max(0.0, min(1.0, number))
    return None


class WhisperCppSTT:
    """Single-worker whisper.cpp wrapper. Lazy-loads one GGML model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: Any = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-stt")

    @property
    def backend_name(self) -> str:
        return "whisper.cpp"

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def model_path(self) -> str:
        return str(self._settings.stt_model_file)

    def model_file_present(self) -> bool:
        path = self._settings.stt_model_file
        return path.is_file() and path.stat().st_size > 0

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            path = self._settings.stt_model_file
            if not path.is_file():
                raise STTModelNotFoundError(
                    f"Whisper GGML model not found at {path}. "
                    "Run: python scripts/download_model.py --stt"
                )
            try:
                from pywhispercpp.model import ContextParams, Model
            except ImportError as exc:
                raise STTModelLoadError(
                    "pywhispercpp is not installed. "
                    "Activate the venv and run: pip install -r requirements.txt"
                ) from exc

            n_threads = self._settings.stt_n_threads or _default_thread_count()
            logger.info(
                "Loading Whisper GGML path=%s n_threads=%s use_gpu=%s",
                path,
                n_threads,
                self._settings.stt_use_gpu,
            )
            started = time.perf_counter()
            try:
                context = ContextParams()
                context["use_gpu"] = bool(self._settings.stt_use_gpu)
                self._model = Model(
                    str(path),
                    n_threads=n_threads,
                    context_params=context,
                    redirect_whispercpp_logs_to=False,
                )
            except Exception as exc:
                self._model = None
                raise STTModelLoadError(f"Failed to load Whisper model at {path}: {exc}") from exc
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("Whisper model loaded in %.0f ms", elapsed_ms)

    def unload(self) -> None:
        with self._lock:
            self._model = None
        logger.info("Whisper model unloaded")

    def shutdown(self) -> None:
        self.unload()
        self._executor.shutdown(wait=False)

    def _transcribe_sync(
        self,
        audio_path: Path,
        language: Optional[str],
        session_id: str,
    ) -> Transcript:
        self.load()
        assert self._model is not None
        lang = normalize_language(language if language is not None else self._settings.stt_language)
        extra = {"session_id": session_id}
        logger.info(
            "STT transcribe file=%s language=%s",
            audio_path.name,
            lang or "auto",
            extra=extra,
        )
        params: dict[str, Any] = {
            "print_progress": False,
            "print_realtime": False,
            "single_segment": True,
            "no_context": True,
        }
        if lang:
            params["language"] = lang
        else:
            params["language"] = "auto"

        started = time.perf_counter()
        try:
            segments = self._model.transcribe(
                str(audio_path),
                extract_probability=True,
                **params,
            )
        except TypeError:
            segments = self._model.transcribe(str(audio_path), **params)
        except Exception as exc:
            raise STTError(f"Whisper transcription failed: {exc}") from exc
        latency_ms = (time.perf_counter() - started) * 1000

        parsed: list[TranscriptSegment] = []
        for segment in segments or []:
            text = (getattr(segment, "text", None) or str(segment)).strip()
            if not text:
                continue
            start_ms, end_ms = _segment_times_ms(segment)
            parsed.append(
                TranscriptSegment(
                    text=text,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    confidence=_segment_confidence(segment),
                )
            )

        text = " ".join(part.text for part in parsed).strip()
        confidences = [part.confidence for part in parsed if part.confidence is not None]
        confidence = sum(confidences) / len(confidences) if confidences else None
        duration_ms = parsed[-1].end_ms if parsed else 0.0
        result = Transcript(
            text=text,
            language=lang,
            confidence=None if confidence is None else round(confidence, 4),
            segments=parsed,
            duration_ms=round(duration_ms, 1),
            latency_ms=round(latency_ms, 1),
            model_path=self.model_path,
        )
        logger.info(
            "STT complete chars=%s latency_ms=%s confidence=%s",
            len(result.text),
            result.latency_ms,
            result.confidence,
            extra=extra,
        )
        return result

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: Optional[str] = None,
        session_id: str = "-",
    ) -> Transcript:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._transcribe_sync(audio_path, language, session_id),
        )
