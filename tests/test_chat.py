from server.ai.llm import ModelNotFoundError


def test_chat_requires_auth(client):
    response = client.post(
        "/v1/chat",
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 401


def test_chat_accepts_x_jarvis_token(client, fake_llm):
    response = client.post(
        "/v1/chat",
        headers={"X-Jarvis-Token": "test-token"},
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "response"
    assert body["message"] == fake_llm.reply
    assert body["usage"]["total_tokens"] == 15
    assert body["session_id"]


def test_chat_accepts_bearer_token(client):
    response = client.post(
        "/v1/chat",
        headers={"Authorization": "Bearer test-token"},
        json={"messages": [{"role": "user", "content": "Ping"}]},
    )
    assert response.status_code == 200
    assert response.json()["message"]


def test_chat_rejects_empty_messages(client):
    response = client.post(
        "/v1/chat",
        headers={"X-Jarvis-Token": "test-token"},
        json={"messages": []},
    )
    assert response.status_code == 422


def test_chat_rejects_stream_flag(client):
    response = client.post(
        "/v1/chat",
        headers={"X-Jarvis-Token": "test-token"},
        json={"messages": [{"role": "user", "content": "Hello"}], "stream": True},
    )
    assert response.status_code == 400


def test_chat_preserves_session_id(client):
    response = client.post(
        "/v1/chat",
        headers={"X-Jarvis-Token": "test-token"},
        json={
            "messages": [{"role": "user", "content": "Hello"}],
            "session_id": "session-123",
        },
    )
    assert response.status_code == 200
    assert response.json()["session_id"] == "session-123"


def test_chat_returns_503_when_model_missing(client, fake_llm):
    fake_llm.fail_with = ModelNotFoundError("GGUF model not found")
    response = client.post(
        "/v1/chat",
        headers={"X-Jarvis-Token": "test-token"},
        json={"messages": [{"role": "user", "content": "Hello"}]},
    )
    assert response.status_code == 503
    assert "GGUF" in response.json()["detail"]
