import json


def _headers():
    return {"X-Jarvis-Token": "test-token"}


def test_memory_requires_auth(client):
    assert client.get("/v1/memory").status_code == 401


def test_memory_summary_and_seeded_preference(client):
    response = client.get("/v1/memory", headers=_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["preferences"] >= 1
    prefs = client.get("/v1/memory/preferences", headers=_headers()).json()
    keys = {item["key"] for item in prefs["preferences"]}
    assert "default_projects_directory" in keys


def test_put_and_get_alias(client):
    put = client.put(
        "/v1/memory/aliases",
        headers=_headers(),
        json={"name": "editor", "kind": "application", "value": "Visual Studio Code"},
    )
    assert put.status_code == 200
    listed = client.get("/v1/memory/aliases", headers=_headers(), params={"kind": "application"}).json()
    assert any(item["name"] == "editor" for item in listed["aliases"])


def test_reject_secret_preference_key(client):
    response = client.put(
        "/v1/memory/preferences",
        headers=_headers(),
        json={"key": "api_token", "value": "secret"},
    )
    assert response.status_code == 400


def test_remember_phrase_skips_llm(client, fake_llm):
    fake_llm.reply = "this should not be used"
    response = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "My projects are normally inside ~/Code.", "session_id": "mem-1"},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["tool"] == "remember_preference"
    assert body["executed"] is True
    assert body["reason"] == "remembered"
    assert fake_llm.call_count == 0
    prefs = client.get("/v1/memory/preferences", headers=_headers()).json()
    values = {item["key"]: item["value"] for item in prefs["preferences"]}
    assert values["default_projects_directory"] == "~/Code"


def test_create_folder_bare_name_uses_projects_dir(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "create_folder",
            "target": "windows",
            "arguments": {"path": "TestApp"},
        }
    )
    response = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "Create a React project called TestApp.", "session_id": "mem-2", "target": "windows"},
    )
    body = response.json()
    assert body["type"] == "confirmation_required"
    assert body["arguments"]["path"] == "~/Projects/TestApp"


def test_history_records_remember(client):
    client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "My projects are normally inside ~/Projects.", "session_id": "mem-3"},
    )
    history = client.get("/v1/memory/history", headers=_headers()).json()["history"]
    assert history
    assert history[0]["tool"] == "remember_preference"
    assert history[0]["executed"] is True
