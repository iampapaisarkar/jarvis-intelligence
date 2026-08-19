from __future__ import annotations

import io
import math
import wave
from array import array
from pathlib import Path

from server.ai.stt import STTModelNotFoundError
from server.utils.audio import write_wav_mono16k
import numpy as np


def _sine_wav_bytes(seconds: float = 0.4, rate: int = 16000) -> bytes:
    n = int(seconds * rate)
    samples = array("h", [int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(n)])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as dest:
        dest.setnchannels(1)
        dest.setsampwidth(2)
        dest.setframerate(rate)
        dest.writeframes(samples.tobytes())
    return buf.getvalue()


def test_transcribe_requires_auth(client):
    response = client.post(
        "/v1/transcribe",
        files={"audio": ("cmd.wav", _sine_wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 401


def test_transcribe_wav_upload(client, fake_stt):
    response = client.post(
        "/v1/transcribe",
        headers={"X-Jarvis-Token": "test-token"},
        files={"audio": ("cmd.wav", _sine_wav_bytes(), "audio/wav")},
        data={"language": "en", "session_id": "voice-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "transcript"
    assert body["text"] == "open visual studio code"
    assert body["confidence"] == 0.91
    assert body["session_id"] == "voice-1"
    assert body["source"] == "upload"
    assert fake_stt.last_language == "en"
    assert fake_stt.last_path is not None
    assert fake_stt.last_path.suffix == ".wav"


def test_transcribe_rejects_non_wav(client):
    response = client.post(
        "/v1/transcribe",
        headers={"X-Jarvis-Token": "test-token"},
        files={"audio": ("cmd.mp3", b"ID3fake", "audio/mpeg")},
    )
    assert response.status_code == 400


def test_transcribe_rejects_invalid_wav(client):
    response = client.post(
        "/v1/transcribe",
        headers={"X-Jarvis-Token": "test-token"},
        files={"audio": ("cmd.wav", b"not a wav", "audio/wav")},
    )
    assert response.status_code == 400


def test_transcribe_returns_503_when_model_missing(client, fake_stt):
    fake_stt.fail_with = STTModelNotFoundError("Whisper GGML model not found")
    response = client.post(
        "/v1/transcribe",
        headers={"X-Jarvis-Token": "test-token"},
        files={"audio": ("cmd.wav", _sine_wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 503


def test_listen_records_then_transcribes(client, fake_stt, monkeypatch):
    def fake_record(dest: Path, *, duration_seconds: float, sample_rate: int, device=None):
        samples = np.zeros(int(duration_seconds * sample_rate), dtype=np.int16)
        write_wav_mono16k(dest, samples, sample_rate)
        return duration_seconds

    monkeypatch.setattr("server.api.speech.record_microphone", fake_record)
    response = client.post(
        "/v1/listen",
        headers={"X-Jarvis-Token": "test-token"},
        json={"duration_seconds": 2, "language": "bn", "session_id": "mic-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "microphone"
    assert body["session_id"] == "mic-1"
    assert body["text"] == fake_stt.reply
    assert fake_stt.last_language == "bn"
