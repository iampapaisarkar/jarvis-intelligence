from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from server.ai.stt import (
    STTError,
    STTModelLoadError,
    STTModelNotFoundError,
    SpeechToText,
    Transcript,
)
from server.api.schemas import ListenRequest, TranscriptResponse, TranscriptSegmentOut
from server.config import Settings, get_settings
from server.dependencies import get_stt_engine
from server.utils.audio import AudioError, MicrophoneError, prepare_wav_for_whisper, record_microphone
from server.utils.logger import get_logger
from server.utils.security import verify_auth_token

router = APIRouter(tags=["speech"])
logger = get_logger("jarvis.speech")

_ALLOWED_SUFFIXES = {".wav"}
_ALLOWED_CONTENT = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "application/octet-stream",
}


def _to_response(
    result: Transcript,
    *,
    session_id: str,
    source: str,
) -> TranscriptResponse:
    return TranscriptResponse(
        text=result.text,
        language=result.language,
        confidence=result.confidence,
        segments=[
            TranscriptSegmentOut(
                text=seg.text,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                confidence=seg.confidence,
            )
            for seg in result.segments
        ],
        duration_ms=result.duration_ms,
        latency_ms=result.latency_ms,
        model=result.model_path,
        session_id=session_id,
        source=source,  # type: ignore[arg-type]
    )


async def _run_stt(
    engine: SpeechToText,
    wav_path: Path,
    *,
    language: str | None,
    session_id: str,
) -> Transcript:
    try:
        return await engine.transcribe(wav_path, language=language, session_id=session_id)
    except STTModelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except STTModelLoadError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except STTError as exc:
        logger.exception("STT error", extra={"session_id": session_id})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local speech recognition failed. See server logs.",
        ) from exc


@router.post(
    "/v1/transcribe",
    response_model=TranscriptResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def transcribe_upload(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
    engine: SpeechToText = Depends(get_stt_engine),
) -> TranscriptResponse:
    sid = session_id or str(uuid.uuid4())
    filename = audio.filename or "audio.wav"
    suffix = Path(filename).suffix.lower() or ".wav"
    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phase 2 accepts WAV files only (16-bit PCM preferred).",
        )
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

    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis-stt-"))
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
        result = await _run_stt(engine, wav_path, language=language, session_id=sid)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info(
        "transcribe upload chars=%s",
        len(result.text),
        extra={"session_id": sid},
    )
    return _to_response(result, session_id=sid, source="upload")


@router.post(
    "/v1/listen",
    response_model=TranscriptResponse,
    dependencies=[Depends(verify_auth_token)],
)
async def listen_microphone(
    body: ListenRequest,
    settings: Settings = Depends(get_settings),
    engine: SpeechToText = Depends(get_stt_engine),
) -> TranscriptResponse:
    sid = body.session_id or str(uuid.uuid4())
    if body.duration_seconds > settings.stt_max_audio_seconds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"duration_seconds cannot exceed {settings.stt_max_audio_seconds}",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis-mic-"))
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
        result = await _run_stt(engine, wav_path, language=body.language, session_id=sid)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    logger.info(
        "listen microphone chars=%s duration=%s",
        len(result.text),
        body.duration_seconds,
        extra={"session_id": sid},
    )
    return _to_response(result, session_id=sid, source="microphone")
