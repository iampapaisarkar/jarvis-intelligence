from server.ai.tts import TTSModelNotFoundError, contains_bengali, normalize_language


def test_speak_requires_auth(client):
    response = client.post("/v1/speak", json={"text": "Hello"})
    assert response.status_code == 401


def test_speak_returns_wav(client, fake_tts):
    response = client.post(
        "/v1/speak",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "Opening Visual Studio Code.", "language": "en", "session_id": "tts-1"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content[:4] == b"RIFF"
    assert response.headers["x-jarvis-session"] == "tts-1"
    assert response.headers["x-jarvis-language"] == "en"
    assert fake_tts.last_text == "Opening Visual Studio Code."
    assert fake_tts.last_language == "en"
    assert fake_tts.last_play is False


def test_speak_play_flag(client, fake_tts):
    response = client.post(
        "/v1/speak",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "Done.", "play": True},
    )
    assert response.status_code == 200
    assert fake_tts.last_play is True


def test_speak_rejects_empty_text(client):
    response = client.post(
        "/v1/speak",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": ""},
    )
    assert response.status_code == 422


def test_speak_returns_503_when_voice_missing(client, fake_tts):
    fake_tts.fail_with = TTSModelNotFoundError("Piper voice not found")
    response = client.post(
        "/v1/speak",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "Hello"},
    )
    assert response.status_code == 503


def test_normalize_language_and_bengali_script():
    assert normalize_language("Bangla") == "bn"
    assert normalize_language("en") == "en"
    assert contains_bengali("জি স্যার") is True
    assert contains_bengali("Open VS Code") is False
