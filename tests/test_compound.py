from pathlib import Path

from server.ai.compound import parse_compound_opens, parse_create_project, parse_open_web
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


def test_create_nodejs_project_phrase():
    steps = parse_create_project(
        "Can you create a NodeJS project?",
        target="mac",
        session_id="s",
    )
    assert steps is not None
    assert steps[0].tool == "create_project"
    assert steps[0].arguments["kind"] == "node"
    assert steps[0].arguments["name"] == "node-app"


def test_create_not_just_project_title_is_demo_user():
    steps = parse_create_project(
        "I told you create a not just project project title is demo user",
        target="mac",
        session_id="s",
    )
    assert steps is not None
    assert steps[0].arguments["kind"] == "node"
    assert steps[0].arguments["name"] == "demo user"


def test_create_project_writes_node_files(client, fake_llm, app_launcher):
    fake_llm.reply = "unused"
    response = client.post(
        "/v1/intent",
        headers={"X-Jarvis-Token": "test-token"},
        json={
            "text": "Create a node js project called demo user",
            "session_id": "node-1",
            "target": "windows",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert fake_llm.call_count == 0
    assert body["executed"] is True
    assert body["tool"] == "create_project"
    folder = Path.home() / "Projects" / "demo-user"
    assert (folder / "package.json").is_file()
    assert (folder / "index.js").is_file()
    assert any("Visual Studio Code" in call for call in app_launcher.calls)
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


def test_open_song_in_youtube_phrase():
    steps = parse_open_web(
        "open xyz song in youtube",
        target="mac",
        session_id="s",
    )
    assert steps is not None
    assert steps[0].tool == "open_url"
    url = steps[0].arguments["url"]
    assert "youtube.com/results" in url
    assert "xyz" in url and "song" in url


def test_open_installed_app_by_spoken_name():
    steps = parse_compound_opens("open Messages", target="mac", session_id="s")
    assert steps is not None
    assert steps[0].tool == "open_application"
    assert steps[0].arguments["application"] == "Messages"


def test_create_react_project_phrase():
    steps = parse_create_project(
        "create a react project called shop",
        target="mac",
        session_id="s",
    )
    assert steps is not None
    assert steps[0].arguments["kind"] == "react"
    assert steps[0].arguments["name"] == "shop"


def test_youtube_intent_opens_browser(client, fake_llm, app_launcher):
    fake_llm.reply = "unused"
    response = client.post(
        "/v1/intent",
        headers={"X-Jarvis-Token": "test-token"},
        json={
            "text": "open xyz song in youtube",
            "session_id": "yt-1",
            "target": "windows",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert fake_llm.call_count == 0
    assert body["executed"] is True
    assert body["tool"] == "open_url"
    assert any("youtube.com" in part for call in app_launcher.calls for part in call)


def test_create_react_project_writes_files(client, fake_llm, app_launcher):
    fake_llm.reply = "unused"
    response = client.post(
        "/v1/intent",
        headers={"X-Jarvis-Token": "test-token"},
        json={
            "text": "Create a react project called shop",
            "session_id": "react-1",
            "target": "windows",
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["executed"] is True
    folder = Path.home() / "Projects" / "shop"
    assert (folder / "package.json").is_file()
    assert (folder / "src" / "App.jsx").is_file()
