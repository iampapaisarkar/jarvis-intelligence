def test_health_ok_when_model_file_present(client, fake_llm):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["backend"] == "fake"
    assert body["model_file_present"] is True
    assert body["model_loaded"] is False
    assert body["version"]


def test_health_degraded_when_model_missing(client, fake_llm):
    fake_llm.present = False
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["model_file_present"] is False


def test_health_does_not_require_auth(client):
    response = client.get("/health")
    assert response.status_code == 200
