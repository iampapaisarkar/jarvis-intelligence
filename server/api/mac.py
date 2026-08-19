from __future__ import annotations

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from server.config import Settings, get_settings
from server.dependencies import get_mac_bridge
from server.mac.bridge import MacBridge
from server.mac.protocol import ErrorMessage, HelloMessage
from server.utils.logger import get_logger
from server.utils.security import extract_token, tokens_match

router = APIRouter(tags=["mac"])
logger = get_logger("jarvis.mac.api")


@router.websocket("/v1/mac")
async def mac_client_socket(
    websocket: WebSocket,
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    bridge: MacBridge = Depends(get_mac_bridge),
) -> None:
    provided = extract_token(websocket.headers.get("x-jarvis-token"), websocket.headers.get("authorization")) or token
    if settings.auth_required and not tokens_match(provided, settings.jarvis_auth_token):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    try:
        first = await websocket.receive_text()
    except WebSocketDisconnect:
        return
    hello = bridge.handshake_hello(first)
    if isinstance(hello, ErrorMessage):
        await websocket.send_json(hello.model_dump())
        await websocket.close(code=1008)
        return
    assert isinstance(hello, HelloMessage)
    await bridge.attach(websocket, hello.hostname, hello.version)
    await websocket.send_json(bridge.hello_ok())
    try:
        while True:
            raw = await websocket.receive_text()
            reply = await bridge.handle_text(raw)
            if reply is not None:
                await websocket.send_json(reply)
    except WebSocketDisconnect:
        await bridge.detach(websocket)
    except Exception:
        logger.exception("mac websocket failed")
        await bridge.detach(websocket)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
