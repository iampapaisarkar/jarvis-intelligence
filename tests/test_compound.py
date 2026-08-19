from pathlib import Path

from server.ai.compound import parse_compound_opens
from server.ai.stt import looks_wrong_language


def test_compound_open_slack_and_gurbly_in_vscode():
    steps = parse_compound_opens(
        "Open Slack and open the 'gurbly' project in VS Code",
        target="mac",
        session_id="s",
    )
    assert steps is not None
    assert len(steps) == 2
    assert steps[0].tool == "open_application"
    assert steps[0].arguments["application"] == "Slack"
    assert steps[1].tool == "open_path"
    assert steps[1].arguments["path"] == "gurbly"
    assert steps[1].arguments["application"] == "Visual Studio Code"


def test_open_project_in_vscode_is_open_path():
    steps = parse_compound_opens(
        "open the gurbly project in visual studio code",
        target="mac",
        session_id="s",
    )
    assert steps is not None
    assert steps[0].tool == "open_path"
    assert steps[0].arguments["path"] == "gurbly"


def test_chitchat_is_not_a_compound_open():
    assert parse_compound_opens("can you hear me?", target="mac", session_id="s") is None


def test_tamil_script_is_wrong_language():
    assert looks_wrong_language("பாங்களா பாங்களா") is True
    assert looks_wrong_language("Atakon var oğlu") is True
    assert looks_wrong_language("open slack") is False
    assert looks_wrong_language("জি স্যার") is False


def test_compound_intent_executes_both_opens(client, fake_llm, app_launcher):
    project = Path.home() / "Projects" / "gurbly"
    project.mkdir(parents=True)
    fake_llm.reply = "unused"
    response = client.post(
        "/v1/intent",
        headers={"X-Jarvis-Token": "test-token"},
        json={
            "text": "Open Slack and open the gurbly project in VS Code",
            "session_id": "compound-1",
            "target": "windows",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert fake_llm.call_count == 0
    assert "Slack" in body["spoken_reply"]
    assert body["executed"] is True
    assert any(call[:3] == ["open", "-a", "Slack"] for call in app_launcher.calls)
    assert any("Visual Studio Code" in call for call in app_launcher.calls)
