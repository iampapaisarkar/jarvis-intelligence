import asyncio
import json

import pytest
from starlette.websockets import WebSocketDisconnect

from server.mac.bridge import MacBridge
from server.mac.protocol import ErrorMessage, HelloMessage
from server.tools.catalog import default_registry
from server.tools.executor import ToolResult


def _hello() -> dict:
    return {
        "type": "hello",
        "role": "mac-client",
        "hostname": "testhost",
        "version": "0.7.0",
    }


def test_health_mac_disconnected(client):
    body = client.get("/health").json()
    assert body["mac"]["connected"] is False
    assert body["mac"]["hostname"] is None
    assert body["version"]


def test_mac_websocket_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/v1/mac?token=wrong"):
            pass
    assert excinfo.value.code == 1008


def test_mac_websocket_hello_and_unknown_type(client):
    with client.websocket_connect("/v1/mac?token=test-token") as ws:
        ws.send_json(_hello())
        ok = ws.receive_json()
        assert ok["type"] == "hello_ok"
        assert ok["session_id"]
        health = client.get("/health").json()
        assert health["mac"]["connected"] is True
        assert health["mac"]["hostname"] == "testhost"
        assert health["mac"]["version"] == "0.7.0"
        ws.send_json({"type": "nope"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["error"] == "unknown_message"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}
    assert client.get("/health").json()["mac"]["connected"] is False


def test_mac_websocket_first_message_must_be_hello(client):
    with client.websocket_connect("/v1/mac?token=test-token") as ws:
        ws.send_json({"type": "ping"})
        err = ws.receive_json()
        assert err["error"] == "unknown_message"
        with pytest.raises(WebSocketDisconnect) as excinfo:
            ws.receive_json()
        assert excinfo.value.code == 1008


def test_intent_mac_executes_when_bridge_connected(client, fake_llm):
    from server.dependencies import get_mac_bridge

    class FakeMacBridge:
        connected = True
        hostname = "testhost"
        client_version = "0.7.0"

        async def run_tool(self, spec, *, arguments, session_id):
            return ToolResult(
                ok=True,
                executed=True,
                spoken="Opening Visual Studio Code.",
                reason="executed",
                data={"application": arguments["application"]},
            )

    client.app.dependency_overrides[get_mac_bridge] = lambda: FakeMacBridge()
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
    body = response.json()
    assert response.status_code == 200
    assert body["executed"] is True
    assert body["reason"] == "executed"
    assert body["target"] == "mac"
    assert body["result"]["application"] == "Visual Studio Code"


def test_handshake_hello_rejects_unknown_type():
    bridge = MacBridge()
    result = bridge.handshake_hello(json.dumps({"type": "ping"}))
    assert isinstance(result, ErrorMessage)
    assert result.error == "unknown_message"


def test_handshake_hello_accepts_valid_payload():
    bridge = MacBridge()
    result = bridge.handshake_hello(json.dumps(_hello()))
    assert isinstance(result, HelloMessage)
    assert result.hostname == "testhost"


def test_bridge_run_tool_completes_from_result():
    async def _run() -> ToolResult:
        class FakeWS:
            def __init__(self) -> None:
                self.sent: list[dict] = []

            async def send_json(self, data: dict) -> None:
                self.sent.append(data)

        bridge = MacBridge(timeout_seconds=2)
        ws = FakeWS()
        await bridge.attach(ws, "host", "0.7.0")
        task = asyncio.create_task(
            bridge.run_tool(
                default_registry().require("get_system_info"),
                arguments={},
                session_id="sess",
            )
        )
        for _ in range(20):
            await asyncio.sleep(0)
            if ws.sent:
                break
        request_id = ws.sent[0]["request_id"]
        reply = await bridge.handle_text(
            json.dumps(
                {
                    "type": "tool_result",
                    "request_id": request_id,
                    "ok": True,
                    "executed": True,
                    "spoken": "This computer is Darwin.",
                    "reason": "executed",
                    "data": {"system": "Darwin"},
                }
            )
        )
        assert reply is None
        return await task

    result = asyncio.run(_run())
    assert result.executed is True
    assert result.data["system"] == "Darwin"


def test_bridge_run_tool_deferred_when_disconnected():
    async def _run() -> ToolResult:
        bridge = MacBridge()
        return await bridge.run_tool(
            default_registry().require("get_system_info"),
            arguments={},
            session_id="sess",
        )

    result = asyncio.run(_run())
    assert result.executed is False
    assert result.reason == "deferred_mac"
