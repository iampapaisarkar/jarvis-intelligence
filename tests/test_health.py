def test_health_ok_when_model_file_present(client, fake_llm, fake_stt):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["voice_ready"] is True
    assert body["llm"]["backend"] == "fake"
    assert body["llm"]["model_file_present"] is True
    assert body["llm"]["model_loaded"] is False
    assert body["stt"]["backend"] == "fake-whisper"
    assert body["stt"]["model_file_present"] is True
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


def test_health_does_not_require_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
