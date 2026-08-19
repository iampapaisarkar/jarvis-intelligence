from pathlib import Path

import numpy as np

from server.ai.wake import command_or_fallback, match_wake_word
from server.utils.audio import write_wav_mono16k
from mac_client.wake import brain_http_base


def test_wake_word_at_start_with_command():
    match = match_wake_word("Jarvis, open visual studio code")
    assert match.heard is True
    assert match.command.lower().startswith("open visual")


def test_hey_jarvis_prefix():
    match = match_wake_word("hey Jarvis")
    assert match.heard is True
    assert match.command == ""


def test_bangla_alias():
    match = match_wake_word("জার্ভিস chrome খোলো")
    assert match.heard is True
    assert "chrome" in match.command.lower()


def test_wake_word_not_in_the_middle():
    match = match_wake_word("please tell Jarvis to open chrome")
    assert match.heard is False
    assert command_or_fallback(match, fallback=False) == ""
    assert command_or_fallback(match, fallback=True) == match.transcript


def test_blank_audio_is_not_a_command():
    from server.ai.wake import is_junk_transcript

    assert is_junk_transcript("[BLANK_AUDIO]") is True
    assert is_junk_transcript("[Motor]") is True
    assert is_junk_transcript("Thank you.") is True
    assert is_junk_transcript("open safari") is False
    match = match_wake_word("[BLANK_AUDIO]")
    assert command_or_fallback(match, fallback=True) == ""


def test_wake_detect_requires_auth(client):
    response = client.post("/v1/wake/detect", json={"text": "Jarvis hello"})
    assert response.status_code == 401


def test_wake_detect_text(client):
    response = client.post(
        "/v1/wake/detect",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "Jarvis open chrome", "session_id": "wake-1"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["type"] == "wake"
    assert body["heard"] is True
    assert body["command"] == "open chrome"
    assert body["source"] == "text"
    assert body["session_id"] == "wake-1"


def test_wake_detect_miss_without_fallback(client):
    response = client.post(
        "/v1/wake/detect",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "open chrome", "fallback": False},
    )
    body = response.json()
    assert body["heard"] is False
    assert body["command"] == ""
    assert body["fallback_used"] is False


def test_wake_detect_miss_with_fallback(client):
    response = client.post(
        "/v1/wake/detect",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "open chrome", "fallback": True},
    )
    body = response.json()
    assert body["heard"] is False
    assert body["command"] == "open chrome"
    assert body["fallback_used"] is True


def test_wake_audio_uses_stt(client, fake_stt, tmp_path):
    fake_stt.reply = "Jarvis open visual studio code"
    wav = tmp_path / "wake.wav"
    write_wav_mono16k(wav, np.zeros(1600, dtype=np.int16), 16000)
    response = client.post(
        "/v1/wake/audio",
        headers={"X-Jarvis-Token": "test-token"},
        files={"audio": ("wake.wav", wav.read_bytes(), "audio/wav")},
        data={"language": "en", "session_id": "wake-audio"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["heard"] is True
    assert "open visual studio code" in body["command"].lower()
    assert body["source"] == "upload"


def test_wake_listen_ptt_fallback(client, fake_stt, monkeypatch):
    fake_stt.reply = "open visual studio code"

    def fake_record(dest: Path, *, duration_seconds: float, sample_rate: int, device=None):
        write_wav_mono16k(dest, np.zeros(int(duration_seconds * sample_rate), dtype=np.int16), sample_rate)
        return duration_seconds

    monkeypatch.setattr("server.api.wake.record_microphone", fake_record)
    response = client.post(
        "/v1/wake/listen",
        headers={"X-Jarvis-Token": "test-token"},
        json={"duration_seconds": 2, "fallback": True, "session_id": "wake-mic"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["heard"] is False
    assert body["command"] == "open visual studio code"
    assert body["fallback_used"] is True
    assert body["source"] == "microphone"


def test_wake_audio_blank_fallback_is_empty(client, fake_stt, tmp_path):
    fake_stt.reply = "[BLANK_AUDIO]"
    wav = tmp_path / "wake.wav"
    write_wav_mono16k(wav, np.zeros(1600, dtype=np.int16), 16000)
    response = client.post(
        "/v1/wake/audio",
        headers={"X-Jarvis-Token": "test-token"},
        files={"audio": ("wake.wav", wav.read_bytes(), "audio/wav")},
        data={"fallback": "true"},
    )
    body = response.json()
    assert body["heard"] is False
    assert body["command"] == ""


def test_quiet_clip_detected(tmp_path):
    from server.utils.audio import clip_is_quiet

    wav = tmp_path / "quiet.wav"
    write_wav_mono16k(wav, np.zeros(16000, dtype=np.int16), 16000)
    assert clip_is_quiet(wav) is True
    loud = tmp_path / "loud.wav"
    write_wav_mono16k(loud, np.full(16000, 2000, dtype=np.int16), 16000)
    assert clip_is_quiet(loud) is False


def test_brain_http_base_from_ws_url():
    assert brain_http_base("ws://127.0.0.1:8765/v1/mac") == "http://127.0.0.1:8765"
    assert brain_http_base("wss://jarvis.local:8765/v1/mac") == "https://jarvis.local:8765"
