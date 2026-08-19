from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from server.ai.tts import TTSError, TTSModelLoadError, TTSModelNotFoundError, TextToSpeech
from server.api.schemas import SpeakRequest
from server.dependencies import get_tts_engine
from server.utils.logger import get_logger
from server.utils.security import verify_auth_token

router = APIRouter(tags=["speech"])
logger = get_logger("jarvis.tts.api")


@router.post(
    "/v1/speak",
    responses={200: {"content": {"audio/wav": {}}}},
    dependencies=[Depends(verify_auth_token)],
)
async def speak(
    body: SpeakRequest,
    engine: TextToSpeech = Depends(get_tts_engine),
) -> FileResponse:
    sid = body.session_id or str(uuid.uuid4())
    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis-tts-"))
    wav_path = tmp_dir / "speech.wav"
    try:
        result = await engine.speak(
            body.text,
            body.language,
            dest=wav_path,
            play=body.play,
            session_id=sid,
        )
    except TTSModelNotFoundError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TTSModelLoadError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except TTSError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("Unexpected TTS failure", extra={"session_id": sid})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Local speech synthesis failed. See server logs.",
        )

    logger.info(
        "speak complete backend=%s duration_ms=%s",
        result.backend,
        result.duration_ms,
        extra={"session_id": sid},
    )
    return FileResponse(
        path=result.path,
        media_type="audio/wav",
        filename="jarvis.wav",
        background=BackgroundTask(shutil.rmtree, tmp_dir, True),
        headers={
            "X-Jarvis-Session": sid,
            "X-Jarvis-Language": result.language,
            "X-Jarvis-Voice": result.voice,
            "X-Jarvis-Backend": result.backend,
            "X-Jarvis-Latency-Ms": str(result.latency_ms),
            "X-Jarvis-Duration-Ms": str(result.duration_ms),
            "X-Jarvis-Fallback": "true" if result.fallback else "false",
        },
    )
