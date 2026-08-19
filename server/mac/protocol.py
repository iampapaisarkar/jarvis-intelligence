"""Mac client WebSocket messages. Unknown types are rejected."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ALLOWED_FROM_MAC = {"hello", "tool_result", "ping", "pong"}
ALLOWED_FROM_BRAIN = {"hello_ok", "tool_request", "ping", "pong", "error"}


class HelloMessage(BaseModel):
    type: Literal["hello"]
    role: Literal["mac-client"]
    hostname: str = Field(min_length=1, max_length=128)
    version: str = Field(default="", max_length=32)


class HelloOkMessage(BaseModel):
    type: Literal["hello_ok"] = "hello_ok"
    session_id: str


class ToolRequestMessage(BaseModel):
    type: Literal["tool_request"] = "tool_request"
    request_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str = "-"


class ToolResultMessage(BaseModel):
    type: Literal["tool_result"]
    request_id: str
    ok: bool
    executed: bool = False
    spoken: str = ""
    reason: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    error: str
    detail: str = ""
