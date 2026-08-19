import json


def test_tools_requires_auth(client):
    response = client.get("/v1/tools")
    assert response.status_code == 401


def test_list_tools_does_not_expose_execute(client):
    response = client.get("/v1/tools", headers={"X-Jarvis-Token": "test-token"})
    assert response.status_code == 200
    body = response.json()
    assert body["execution"] == "disabled"
    names = [item["name"] for item in body["tools"]]
    assert "open_application" in names
    assert "run_terminal" in names
    assert "delete_path" in names
    assert all("execute" not in item for item in body["tools"])


def test_intent_requires_auth(client):
    response = client.post("/v1/intent", json={"text": "Open VS Code"})
    assert response.status_code == 401


def test_intent_tool_call_is_not_executed(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "open_application",
            "target": "mac",
            "arguments": {"application": "Visual Studio Code"},
            "spoken_reply": "Opening Visual Studio Code.",
        }
    )
    response = client.post(
        "/v1/intent",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "VS Code ta open kore dao.", "target": "mac"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "tool_call"
    assert body["tool"] == "open_application"
    assert body["target"] == "mac"
    assert body["arguments"]["application"] == "Visual Studio Code"
    assert body["executed"] is False
    assert body["risk"] == "low"
    assert body["safety"] == "allowed"
    assert body["confirmed"] is False


def test_intent_clarification(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "clarification",
            "message": "Which folder should I create?",
            "spoken_reply": "Which folder should I create?",
        }
    )
    response = client.post(
        "/v1/intent",
        headers={"X-Jarvis-Token": "test-token"},
        json={"text": "Create a folder"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "clarification"
    assert body["executed"] is False
    assert body["tool"] is None
