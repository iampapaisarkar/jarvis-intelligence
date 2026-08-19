import json


def _headers():
    return {"X-Jarvis-Token": "test-token"}


def test_create_folder_requires_confirmation(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "create_folder",
            "target": "windows",
            "arguments": {"path": "~/Projects/demo"},
        }
    )
    response = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "Create a Projects demo folder", "session_id": "sess-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "confirmation_required"
    assert body["executed"] is False
    assert body["confirmation_id"]
    assert "confirm" in body["spoken_reply"].lower()

    pending = client.get("/v1/pending", headers=_headers(), params={"session_id": "sess-1"})
    assert pending.json()["pending"] is True
    assert pending.json()["confirmation_id"] == body["confirmation_id"]


def test_confirm_yes_creates_folder(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "create_folder",
            "arguments": {"path": "~/Projects/demo"},
        }
    )
    first = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "Make a demo folder", "session_id": "sess-2", "target": "windows"},
    )
    cid = first.json()["confirmation_id"]
    yes = client.post(
        "/v1/confirm",
        headers=_headers(),
        json={"session_id": "sess-2", "confirmation_id": cid, "approved": True},
    )
    body = yes.json()
    assert yes.status_code == 200
    assert body["type"] == "tool_call"
    assert body["confirmed"] is True
    assert body["executed"] is True
    assert body["safety"] == "allowed"
    assert body["tool"] == "create_folder"
    from pathlib import Path

    assert (Path.home() / "Projects" / "demo").is_dir()


def test_spoken_yes_confirms_same_session(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "create_file",
            "arguments": {"path": "~/Projects/notes.txt", "content": "hi"},
        }
    )
    client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "Write notes.txt", "session_id": "sess-3"},
    )
    yes = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "জি", "session_id": "sess-3"},
    )
    body = yes.json()
    assert body["type"] == "tool_call"
    assert body["confirmed"] is True
    assert body["executed"] is True
    from pathlib import Path

    assert (Path.home() / "Projects" / "notes.txt").is_file()


def test_other_session_cannot_confirm(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "create_folder",
            "arguments": {"path": "~/Projects/demo"},
        }
    )
    first = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "Create folder", "session_id": "sess-a"},
    )
    cid = first.json()["confirmation_id"]
    stolen = client.post(
        "/v1/confirm",
        headers=_headers(),
        json={"session_id": "sess-b", "confirmation_id": cid, "approved": True},
    )
    assert stolen.status_code in (403, 404)
    still = client.get("/v1/pending", headers=_headers(), params={"session_id": "sess-a"})
    assert still.json()["pending"] is True


def test_delete_system_path_is_denied(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "delete_path",
            "target": "windows",
            "arguments": {"path": r"C:\Windows"},
        }
    )
    response = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "Delete Windows", "session_id": "sess-deny"},
    )
    body = response.json()
    assert body["type"] == "denied"
    assert body["executed"] is False
    assert body["safety"] == "denied"
    assert body["confirmation_id"] is None


def test_forbidden_terminal_is_denied(client, fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "run_terminal",
            "arguments": {"command": "format c:"},
        }
    )
    response = client.post(
        "/v1/intent",
        headers=_headers(),
        json={"text": "format the disk", "session_id": "sess-fmt"},
    )
    body = response.json()
    assert body["type"] == "denied"
    assert body["executed"] is False
    assert "format" not in body["spoken_reply"].lower()
