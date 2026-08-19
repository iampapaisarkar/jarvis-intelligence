from pathlib import Path

import pytest

from server.ai.tts import PiperTTS
from server.config import REPO_ROOT, Settings
from server.utils.audio import wav_duration_seconds

CANDIDATES = [
    REPO_ROOT / "models" / "tts" / "en_US-ryan-medium.onnx",
    REPO_ROOT / "models" / "tts" / "en_US-lessac-low.onnx",
    REPO_ROOT / "models" / "tts" / "en_US-lessac-medium.onnx",
]


def _first_piper() -> Path | None:
    for path in CANDIDATES:
        if path.is_file() and Path(str(path) + ".json").is_file():
            return path
    tts_dir = REPO_ROOT / "models" / "tts"
    if tts_dir.is_dir():
        for path in sorted(tts_dir.glob("*.onnx")):
            if path.stat().st_size > 1_000_000 and Path(str(path) + ".json").is_file():
                return path
    return None


def test_engine_reports_missing_voice(tmp_path):
    settings = Settings(tts_model_path=tmp_path / "missing.onnx")
    engine = PiperTTS(settings)
    assert engine.model_file_present() is False
    assert engine.loaded is False
    assert engine.backend_name == "piper"
    engine.shutdown()


@pytest.mark.integration
def test_piper_speaks_short_english(tmp_path):
    model = _first_piper()
    if model is None:
        pytest.skip("No Piper voice under models/tts. Run: python scripts/download_model.py --tts")

    dest = tmp_path / "out.wav"
    settings = Settings(tts_model_path=model, tts_use_cuda=False, tts_preload=False)
    engine = PiperTTS(settings)
    try:
        import asyncio

        result = asyncio.run(
            engine.speak(
                "Opening Visual Studio Code.",
                "en",
                dest=dest,
                play=False,
                session_id="integration-tts",
            )
        )
    finally:
        engine.shutdown()

    assert dest.is_file()
    assert dest.stat().st_size > 1000
    assert result.backend == "piper"
    assert result.language == "en"
    assert result.duration_ms > 200
    assert wav_duration_seconds(dest) > 0.2


@pytest.mark.integration
def test_bangla_uses_local_backend(tmp_path):
    model = _first_piper()
    if model is None:
        pytest.skip("No Piper voice under models/tts. Run: python scripts/download_model.py --tts")

    dest = tmp_path / "bn.wav"
    settings = Settings(tts_model_path=model, tts_use_cuda=False)
    engine = PiperTTS(settings)
    try:
        import asyncio
        import shutil

        result = asyncio.run(
            engine.speak(
                "জি স্যার, VS Code খুলছি।",
                "bn",
                dest=dest,
                play=False,
                session_id="integration-tts-bn",
            )
        )
    finally:
        engine.shutdown()

    assert dest.is_file()
    assert dest.stat().st_size > 500
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        assert result.language == "bn"
        assert result.backend in {"espeak-ng", "piper"}
    else:
        assert result.fallback is True or result.language in {"bn", "en"}
