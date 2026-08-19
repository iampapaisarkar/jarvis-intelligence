from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from server.ai.stt import STTError, STTModelLoadError, STTModelNotFoundError, SpeechToText
from server.ai.wake import command_or_fallback, match_wake_word
from server.api.schemas import WakeDetectRequest, WakeListenRequest, WakeResponse
from server.config import Settings, get_settings
from server.dependencies import get_stt_engine
from server.utils.audio import AudioError, MicrophoneError, prepare_wav_for_whisper, record_microphone
from server.utils.logger import get_logger
from server.utils.security import verify_auth_token

router = APIRouter(tags=["wake"])
logger = get_logger("jarvis.wake")

_ALLOWED_SUFFIXES = {".wav"}
_ALLOWED_CONTENT = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "application/octet-stream",
}


def _response(
    *,
    match,
    session_id: str,
    source: str,
    fallback: bool,
    model: str = "",
    language: str | None = None,
    confidence: float | None = None,
    duration_ms: float = 0.0,
    latency_ms: float = 0.0,
) -> WakeResponse:
    return WakeResponse(
        heard=match.heard,
        word=match.word,
        command=command_or_fallback(match, fallback=fallback),
        transcript=match.transcript,
        session_id=session_id,
        source=source,  # type: ignore[arg-type]
        fallback_used=bool(fallback and not match.heard and match.transcript),
        model=model,
        language=language,
        confidence=confidence,
        duration_ms=duration_ms,
        latency_ms=latency_ms,
    )


async def _transcribe_wav(
    engine: SpeechToText,
    wav_path: Path,
    *,
    language: str | None,
    session_id: str,
):
    try:
        return await engine.transcribe(wav_path, language=language, session_id=session_id)
    except STTModelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except STTModelLoadError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except STTError:
        logger.exception("STT error during wake detect", extra={"session_id": session_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local speech recognition failed. See server logs.",
        )


@router.post(
    "/v1/wake/detect",
    response_model=WakeResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def detect_wake_text(
    body: WakeDetectRequest,
    settings: Settings = Depends(get_settings),
) -> WakeResponse:
    if not settings.jarvis_wake_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Wake word is disabled.")
    sid = body.session_id or str(uuid.uuid4())
    match = match_wake_word(body.text, word=settings.jarvis_wake_word)
    logger.info(
        "wake detect heard=%s command_chars=%s",
        match.heard,
        len(match.command),
        extra={"session_id": sid},
    )
    return _response(match=match, session_id=sid, source="text", fallback=body.fallback)


@router.post(
    "/v1/wake/audio",
    response_model=WakeResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def detect_wake_audio(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    fallback: bool = Form(default=False),
    settings: Settings = Depends(get_settings),
    engine: SpeechToText = Depends(get_stt_engine),
) -> WakeResponse:
    if not settings.jarvis_wake_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Wake word is disabled.")
    sid = session_id or str(uuid.uuid4())
    filename = audio.filename or "audio.wav"
    suffix = Path(filename).suffix.lower() or ".wav"
    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wake audio must be a WAV file.")
    if content_type and content_type not in _ALLOWED_CONTENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio content type: {content_type}",
        )
    payload = await audio.read()
    await audio.close()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded audio is empty")
    if len(payload) > settings.stt_max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio exceeds {settings.stt_max_upload_bytes} bytes",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis-wake-"))
    raw_path = tmp_dir / f"upload{suffix}"
    wav_path = tmp_dir / "whisper.wav"
    try:
        raw_path.write_bytes(payload)
        del payload
        try:
            prepare_wav_for_whisper(
                raw_path,
                wav_path,
                max_seconds=settings.stt_max_audio_seconds,
            )
        except AudioError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        result = await _transcribe_wav(engine, wav_path, language=language, session_id=sid)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    match = match_wake_word(result.text, word=settings.jarvis_wake_word)
    return _response(
        match=match,
        session_id=sid,
        source="upload",
        fallback=fallback,
        model=result.model_path,
        language=result.language,
        confidence=result.confidence,
        duration_ms=result.duration_ms,
        latency_ms=result.latency_ms,
    )


@router.post(
    "/v1/wake/listen",
    response_model=WakeResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def listen_for_wake(
    body: WakeListenRequest,
    settings: Settings = Depends(get_settings),
    engine: SpeechToText = Depends(get_stt_engine),
) -> WakeResponse:
    """Microphone capture, then wake detect. `fallback=true` keeps push-to-talk if Jarvis was not said."""
    if not settings.jarvis_wake_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Wake word is disabled.")
    sid = body.session_id or str(uuid.uuid4())
    if body.duration_seconds > settings.stt_max_audio_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"duration_seconds cannot exceed {settings.stt_max_audio_seconds}",
        )
    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis-wake-mic-"))
    wav_path = tmp_dir / "mic.wav"
    try:
        try:
            record_microphone(
                wav_path,
                duration_seconds=body.duration_seconds,
                sample_rate=settings.mic_sample_rate,
            )
        except MicrophoneError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        result = await _transcribe_wav(engine, wav_path, language=body.language, session_id=sid)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    match = match_wake_word(result.text, word=settings.jarvis_wake_word)
    logger.info(
        "wake listen heard=%s fallback=%s",
        match.heard,
        body.fallback,
        extra={"session_id": sid},
    )
    return _response(
        match=match,
        session_id=sid,
        source="microphone",
        fallback=body.fallback,
        model=result.model_path,
        language=result.language,
        confidence=result.confidence,
        duration_ms=result.duration_ms,
        latency_ms=result.latency_ms,
    )
