import asyncio
import json

from server.ai.intent import IntentParser, extract_json_object
from server.config import Settings
from server.tools.catalog import default_registry


def test_extract_json_from_fences_and_prose():
    data = extract_json_object(
        'Sure.\n```json\n{"type":"reply","message":"Hello"}\n```\n'
    )
    assert data["type"] == "reply"
    assert data["message"] == "Hello"


def test_extract_json_requires_object():
    try:
        extract_json_object("not json")
        assert False, "expected parse error"
    except Exception as exc:
        assert "JSON" in str(exc) or "json" in str(exc).lower()


def _parser(fake_llm) -> IntentParser:
    return IntentParser(fake_llm, default_registry(), Settings())


def test_parse_valid_tool_call(fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "open_application",
            "target": "mac",
            "arguments": {"application": "vscode"},
            "spoken_reply": "Opening Visual Studio Code.",
        }
    )
    parsed = asyncio.run(_parser(fake_llm).parse("VS Code ta open kore dao.", session_id="s1"))
    assert parsed.type == "tool_call"
    assert parsed.tool == "open_application"
    assert parsed.target == "mac"
    assert parsed.arguments["application"] == "Visual Studio Code"
    assert parsed.risk == "low"
    assert parsed.requires_confirmation is False
    assert parsed.executed is False
    assert fake_llm.last_json_mode is True


def test_parse_ignores_model_risk_and_uses_registry(fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "create_folder",
            "target": "windows",
            "arguments": {"path": "C:/Users/demo/Projects"},
            "risk": "low",
            "requires_confirmation": False,
        }
    )
    parsed = asyncio.run(_parser(fake_llm).parse("Make a Projects folder.", session_id="s2"))
    assert parsed.risk == "medium"
    assert parsed.requires_confirmation is True
    assert parsed.executed is False


def test_unknown_tool_becomes_clarification(fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "run_terminal",
            "arguments": {"command": "rm -rf /"},
        }
    )
    parsed = asyncio.run(_parser(fake_llm).parse("wipe the disk", session_id="s3"))
    assert parsed.type == "clarification"
    assert parsed.executed is False
    assert parsed.tool is None


def test_invalid_json_retries_then_clarifies(fake_llm):
    fake_llm.replies = [
        "I will open VS Code for you.",
        json.dumps(
            {
                "type": "tool_call",
                "tool": "open_application",
                "target": "windows",
                "arguments": {"application": "Visual Studio Code"},
            }
        ),
    ]
    parsed = asyncio.run(_parser(fake_llm).parse("Open VS Code", session_id="s4"))
    assert parsed.type == "tool_call"
    assert parsed.parse_recovered is True
    assert fake_llm.call_count == 2


def test_reply_intent(fake_llm):
    fake_llm.reply = json.dumps(
        {"type": "reply", "message": "Hello. How can I help?", "spoken_reply": "Hello. How can I help?"}
    )
    parsed = asyncio.run(_parser(fake_llm).parse("Hi Jarvis", session_id="s5"))
    assert parsed.type == "reply"
    assert parsed.message.startswith("Hello")


def test_request_target_overrides_model_target(fake_llm):
    fake_llm.reply = json.dumps(
        {
            "type": "tool_call",
            "tool": "open_application",
            "target": "windows",
            "arguments": {"application": "vscode"},
        }
    )
    parsed = asyncio.run(
        _parser(fake_llm).parse("Open VS Code", session_id="s6", default_target="mac")
    )
    assert parsed.target == "mac"
