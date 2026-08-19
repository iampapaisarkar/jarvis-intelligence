"""Local text-to-speech. Piper for English; optional Piper or espeak-ng for Bangla."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from server.config import Settings
from server.utils.logger import get_logger

logger = get_logger("jarvis.tts")

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


class TTSError(Exception):
    """Raised when local speech synthesis cannot be used."""


class TTSModelNotFoundError(TTSError):
    pass


class TTSModelLoadError(TTSError):
    pass


@dataclass(frozen=True)
class SynthesizedSpeech:
    path: Path
    text: str
    language: str
    voice: str
    backend: str
    sample_rate: int
    duration_ms: float
    latency_ms: float
    fallback: bool = False


class TextToSpeech(Protocol):
    """Abstract local TTS. The rest of Jarvis must not import Piper types."""

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

    async def speak(
        self,
        text: str,
        language: Optional[str] = None,
        *,
        dest: Path,
        play: bool = False,
        session_id: str = "-",
    ) -> SynthesizedSpeech: ...


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
    raise TTSError(f"Unsupported language hint: {value}")


def contains_bengali(text: str) -> bool:
    return any("\u0980" <= ch <= "\u09FF" for ch in text)


def _wav_info(path: Path) -> tuple[int, float]:
    with wave.open(str(path), "rb") as src:
        rate = src.getframerate()
        frames = src.getnframes()
        duration_ms = (frames / float(rate) * 1000.0) if rate else 0.0
        return rate, duration_ms


class PiperTTS:
    """Single-worker Piper wrapper. English ONNX is required; Bangla is optional."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._en_voice: Any = None
        self._bn_voice: Any = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-tts")
        self._espeak_bin = shutil.which("espeak-ng") or shutil.which("espeak")
        self._espeak_has_bn: Optional[bool] = None

    @property
    def backend_name(self) -> str:
        return "piper"

    @property
    def loaded(self) -> bool:
        return self._en_voice is not None

    @property
    def model_path(self) -> str:
        return str(self._settings.tts_model_file)

    def model_file_present(self) -> bool:
        path = self._settings.tts_model_file
        config = Path(str(path) + ".json")
        return path.is_file() and path.stat().st_size > 0 and config.is_file()

    def _bn_piper_file(self) -> Optional[Path]:
        raw = self._settings.tts_bn_model_path
        if raw is None:
            return None
        path = self._settings.resolve_path(raw)
        if path.is_file() and path.stat().st_size > 0 and Path(str(path) + ".json").is_file():
            return path
        return None

    def load(self) -> None:
        with self._lock:
            if self._en_voice is not None:
                return
            path = self._settings.tts_model_file
            config = Path(str(path) + ".json")
            if not path.is_file() or not config.is_file():
                raise TTSModelNotFoundError(
                    f"Piper voice not found at {path} (need .onnx and .onnx.json). "
                    "Run: python scripts/download_model.py --tts"
                )
            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise TTSModelLoadError(
                    "piper-tts is not installed. "
                    "Activate the venv and run: pip install -r requirements.txt"
                ) from exc

            logger.info("Loading Piper voice path=%s use_cuda=%s", path, self._settings.tts_use_cuda)
            started = time.perf_counter()
            try:
                self._en_voice = PiperVoice.load(
                    str(path),
                    config_path=str(config),
                    use_cuda=bool(self._settings.tts_use_cuda),
                )
            except Exception as exc:
                self._en_voice = None
                raise TTSModelLoadError(f"Failed to load Piper voice at {path}: {exc}") from exc
            logger.info("Piper voice loaded in %.0f ms", (time.perf_counter() - started) * 1000)

    def _load_bn_piper(self) -> Any:
        path = self._bn_piper_file()
        if path is None:
            return None
        if self._bn_voice is not None:
            return self._bn_voice
        from piper import PiperVoice

        config = Path(str(path) + ".json")
        logger.info("Loading Bangla Piper voice path=%s", path)
        self._bn_voice = PiperVoice.load(
            str(path),
            config_path=str(config),
            use_cuda=bool(self._settings.tts_use_cuda),
        )
        return self._bn_voice

    def unload(self) -> None:
        with self._lock:
            self._en_voice = None
            self._bn_voice = None
        logger.info("Piper voices unloaded")

    def shutdown(self) -> None:
        self.unload()
        self._executor.shutdown(wait=False)

    def _espeak_supports_bn(self) -> bool:
        if self._espeak_bin is None:
            return False
        if self._espeak_has_bn is not None:
            return self._espeak_has_bn
        try:
            result = subprocess.run(
                [self._espeak_bin, "--voices"],
                check=True,
                capture_output=True,
                text=True,
            )
            found = False
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "bn":
                    found = True
                    break
            self._espeak_has_bn = found
        except (OSError, subprocess.CalledProcessError):
            self._espeak_has_bn = False
        return self._espeak_has_bn

    def _synthesize_espeak(self, text: str, dest: Path, voice: str) -> None:
        assert self._espeak_bin is not None
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [self._espeak_bin, "-v", voice, "-w", str(dest), "--", text],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or "").strip()
            raise TTSError(f"espeak-ng failed: {err or exc}") from exc

    def _synthesize_piper(self, voice: Any, text: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dest), "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)

    def _speak_sync(
        self,
        text: str,
        language: Optional[str],
        dest: Path,
        play: bool,
        session_id: str,
    ) -> SynthesizedSpeech:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise TTSError("Cannot speak empty text")
        if len(cleaned) > self._settings.tts_max_chars:
            raise TTSError(
                f"Text is {len(cleaned)} characters; maximum is {self._settings.tts_max_chars}"
            )

        lang = normalize_language(language)
        want_bn = lang == "bn" or (lang is None and contains_bengali(cleaned))
        extra = {"session_id": session_id}
        logger.info(
            "TTS speak chars=%s language=%s play=%s",
            len(cleaned),
            lang or "auto",
            play,
            extra=extra,
        )
        started = time.perf_counter()
        fallback = False
        backend = "piper"
        voice_name = Path(self.model_path).name
        spoken_lang = "en"

        if want_bn:
            bn_voice = self._load_bn_piper()
            if bn_voice is not None:
                self._synthesize_piper(bn_voice, cleaned, dest)
                voice_name = Path(str(self._bn_piper_file())).name
                spoken_lang = "bn"
            elif self._espeak_supports_bn():
                self._synthesize_espeak(cleaned, dest, "bn")
                backend = "espeak-ng"
                voice_name = "bn"
                spoken_lang = "bn"
            else:
                self.load()
                assert self._en_voice is not None
                self._synthesize_piper(self._en_voice, cleaned, dest)
                fallback = True
                spoken_lang = "en"
                logger.warning(
                    "No Bangla TTS voice installed; used English Piper. "
                    "Install espeak-ng or set TTS_BN_MODEL_PATH.",
                    extra=extra,
                )
        else:
            self.load()
            assert self._en_voice is not None
            self._synthesize_piper(self._en_voice, cleaned, dest)
            spoken_lang = lang or "en"

        latency_ms = (time.perf_counter() - started) * 1000
        sample_rate, duration_ms = _wav_info(dest)
        if play:
            from server.utils.audio import PlaybackError, play_wav

            try:
                play_wav(dest)
            except PlaybackError as exc:
                logger.warning("Playback skipped: %s", exc, extra=extra)

        result = SynthesizedSpeech(
            path=dest,
            text=cleaned,
            language=spoken_lang,
            voice=voice_name,
            backend=backend,
            sample_rate=sample_rate,
            duration_ms=round(duration_ms, 1),
            latency_ms=round(latency_ms, 1),
            fallback=fallback,
        )
        logger.info(
            "TTS complete backend=%s duration_ms=%s latency_ms=%s fallback=%s",
            result.backend,
            result.duration_ms,
            result.latency_ms,
            result.fallback,
            extra=extra,
        )
        return result

    async def speak(
        self,
        text: str,
        language: Optional[str] = None,
        *,
        dest: Path,
        play: bool = False,
        session_id: str = "-",
    ) -> SynthesizedSpeech:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._speak_sync(text, language, dest, play, session_id),
        )
