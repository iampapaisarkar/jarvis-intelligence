"""Single Mac-body connection. The brain never executes Mac tools locally."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from fastapi import WebSocket
from pydantic import ValidationError

from server.mac.protocol import (
    ALLOWED_FROM_MAC,
    ErrorMessage,
    HelloMessage,
    HelloOkMessage,
    ToolRequestMessage,
    ToolResultMessage,
)
from server.tools.base import ToolSpec
from server.tools.executor import ToolResult
from server.utils.logger import get_logger

logger = get_logger("jarvis.mac")


class MacBridge:
    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self._timeout = timeout_seconds
        self._lock = asyncio.Lock()
        self._ws: Optional[WebSocket] = None
        self._hostname: Optional[str] = None
        self._version: Optional[str] = None
        self._pending: dict[str, asyncio.Future[ToolResult]] = {}

    @property
    def connected(self) -> bool:
        return self._ws is not None

    @property
    def hostname(self) -> Optional[str]:
        return self._hostname

    @property
    def client_version(self) -> Optional[str]:
        return self._version

    async def attach(self, ws: WebSocket, hostname: str, version: str) -> None:
        async with self._lock:
            old = self._ws
            self._ws = ws
            self._hostname = hostname
            self._version = version
        if old is not None and old is not ws:
            try:
                await old.close(code=1000)
            except Exception:
                pass
        logger.info("mac client connected hostname=%s version=%s", hostname, version)

    async def detach(self, ws: WebSocket) -> None:
        async with self._lock:
            if self._ws is ws:
                self._ws = None
                self._hostname = None
                self._version = None
        self._fail_pending("The Mac client disconnected.")
        logger.info("mac client disconnected")

    async def run_tool(
        self,
        spec: ToolSpec,
        *,
        arguments: dict[str, Any],
        session_id: str,
    ) -> ToolResult:
        ws = self._ws
        if ws is None:
            return ToolResult(
                ok=True,
                executed=False,
                spoken="I'll do that on the Mac once the client is connected.",
                reason="deferred_mac",
            )
        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ToolResult] = loop.create_future()
        self._pending[request_id] = future
        payload = ToolRequestMessage(
            request_id=request_id,
            tool=spec.name,
            arguments=arguments,
            session_id=session_id,
        )
        try:
            await ws.send_json(payload.model_dump())
        except Exception:
            self._pending.pop(request_id, None)
            return ToolResult(
                ok=False,
                executed=False,
                spoken="I couldn't reach the Mac client.",
                reason="mac_send_failed",
            )
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=self._timeout)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            return ToolResult(
                ok=False,
                executed=False,
                spoken="The Mac client did not respond in time.",
                reason="mac_timeout",
            )

    async def handle_text(self, raw: str) -> Optional[dict[str, Any]]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ErrorMessage(error="invalid_json", detail="Message must be a JSON object.").model_dump()
        if not isinstance(data, dict):
            return ErrorMessage(error="invalid_json", detail="Message must be a JSON object.").model_dump()
        kind = str(data.get("type") or "")
        if kind not in ALLOWED_FROM_MAC:
            return ErrorMessage(error="unknown_message", detail=f"Unsupported type: {kind or 'missing'}").model_dump()
        if kind == "ping":
            return {"type": "pong"}
        if kind == "pong":
            return None
        if kind == "hello":
            return ErrorMessage(error="already_hello", detail="Hello was already accepted.").model_dump()
        if kind == "tool_result":
            try:
                result = ToolResultMessage.model_validate(data)
            except ValidationError:
                return ErrorMessage(error="invalid_result", detail="tool_result was malformed.").model_dump()
            future = self._pending.pop(result.request_id, None)
            if future is not None and not future.done():
                future.set_result(
                    ToolResult(
                        ok=result.ok,
                        executed=result.executed,
                        spoken=result.spoken or ("Done." if result.ok else "The Mac action failed."),
                        reason=result.reason or ("executed" if result.executed else "mac_failed"),
                        data=result.data,
                    )
                )
            return None
        return ErrorMessage(error="unknown_message", detail="Unsupported type.").model_dump()

    def handshake_hello(self, raw: str) -> HelloMessage | ErrorMessage:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ErrorMessage(error="invalid_json", detail="Hello must be JSON.")
        if not isinstance(data, dict) or data.get("type") != "hello":
            return ErrorMessage(error="unknown_message", detail="First message must be hello.")
        try:
            return HelloMessage.model_validate(data)
        except ValidationError:
            return ErrorMessage(error="invalid_hello", detail="Hello was malformed.")

    def hello_ok(self) -> dict[str, Any]:
        return HelloOkMessage(session_id=str(uuid.uuid4())).model_dump()

    def _fail_pending(self, spoken: str) -> None:
        pending = list(self._pending.items())
        self._pending.clear()
        result = ToolResult(ok=False, executed=False, spoken=spoken, reason="mac_disconnected")
        for _, future in pending:
            if not future.done():
                future.set_result(result)
