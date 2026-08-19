def test_health_ok_when_model_file_present(client, fake_llm, fake_stt, fake_tts):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["voice_ready"] is True
    assert body["llm"]["backend"] == "fake"
    assert body["stt"]["backend"] == "fake-whisper"
    assert body["tts"]["backend"] == "fake-piper"
    assert body["tts"]["model_file_present"] is True
    assert body["tools"]["registered"] == 8
    assert body["tools"]["execution"] == "posix"
    assert body["safety"]["policy"] == "local"
    assert body["mac"]["connected"] is False
    assert body["memory"]["ok"] is True
    assert body["memory"]["preferences"] >= 1
    assert body["version"]


def test_health_degraded_when_llm_missing(client, fake_llm):
    fake_llm.present = False
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["voice_ready"] is False
    assert body["llm"]["model_file_present"] is False


def test_health_voice_not_ready_when_stt_missing(client, fake_stt):
    fake_stt.present = False
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["voice_ready"] is False
    assert body["stt"]["model_file_present"] is False


def test_health_voice_not_ready_when_tts_missing(client, fake_tts):
    fake_tts.present = False
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["voice_ready"] is False
    assert body["tts"]["model_file_present"] is False


def test_health_does_not_require_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
