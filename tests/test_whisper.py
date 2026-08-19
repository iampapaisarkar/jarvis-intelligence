from pathlib import Path

import numpy as np
import pytest

from server.ai.stt import WhisperCppSTT, normalize_language
from server.config import REPO_ROOT, Settings
from server.utils.audio import prepare_wav_for_whisper, resample_mono, write_wav_mono16k

CANDIDATES = [
    REPO_ROOT / "models" / "stt" / "ggml-base.bin",
    REPO_ROOT / "models" / "stt" / "ggml-tiny.bin",
    REPO_ROOT / "models" / "stt" / "ggml-base-q5_1.bin",
    REPO_ROOT / "models" / "stt" / "ggml-tiny-q5_1.bin",
]


def _first_whisper() -> Path | None:
    for path in CANDIDATES:
        if path.is_file() and path.stat().st_size > 5_000_000:
            return path
    stt_dir = REPO_ROOT / "models" / "stt"
    if stt_dir.is_dir():
        for path in sorted(stt_dir.glob("ggml-*.bin")):
            if path.stat().st_size > 5_000_000:
                return path
    return None


def test_normalize_language_aliases():
    assert normalize_language("English") == "en"
    assert normalize_language("bangla") == "bn"
    assert normalize_language("bn") == "bn"
    assert normalize_language("auto") is None
    assert normalize_language(None) is None


def test_resample_changes_length():
    samples = np.arange(16000, dtype=np.int16)
    out = resample_mono(samples, 8000, 16000)
    assert len(out) == 32000


def test_prepare_wav_writes_16k_mono(tmp_path):
    source = tmp_path / "in.wav"
    dest = tmp_path / "out.wav"
    write_wav_mono16k(source, np.zeros(8000, dtype=np.int16), 8000)
    duration = prepare_wav_for_whisper(source, dest, max_seconds=5)
    assert dest.is_file()
    assert 0.9 < duration < 1.1


def test_engine_reports_missing_model(tmp_path):
    settings = Settings(stt_model_path=tmp_path / "nope.bin")
    engine = WhisperCppSTT(settings)
    assert engine.model_file_present() is False
    assert engine.loaded is False
    assert engine.backend_name == "whisper.cpp"
    engine.shutdown()


@pytest.mark.integration
def test_local_whisper_transcribes_spoken_command(tmp_path):
    import shutil
    import subprocess

    model = _first_whisper()
    if model is None:
        pytest.skip("No Whisper GGML found under models/stt. Run: python scripts/download_model.py --stt")
    if shutil.which("say") is None:
        pytest.skip("macOS `say` is required to generate a speech fixture")

    wav_path = tmp_path / "command.wav"
    aiff_path = tmp_path / "command.aiff"
    subprocess.run(
        ["say", "-o", str(aiff_path), "open visual studio code"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "afconvert",
            "-f",
            "WAVE",
            "-d",
            "LEI16@16000",
            str(aiff_path),
            str(wav_path),
        ],
        check=True,
        capture_output=True,
    )

    settings = Settings(stt_model_path=model, stt_n_threads=2, stt_preload=False)
    engine = WhisperCppSTT(settings)
    try:
        import asyncio

        result = asyncio.run(
            engine.transcribe(wav_path, language="en", session_id="integration-stt")
        )
    finally:
        engine.shutdown()

    text = result.text.lower()
    assert result.latency_ms > 0
    assert any(word in text for word in ("open", "visual", "studio", "code", "vs")), text
