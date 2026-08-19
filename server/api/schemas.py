from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    backend: str
    model_path: str
    model_file_present: bool
    model_loaded: bool
    n_ctx: int
    n_gpu_layers: int


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=32)
    session_id: Optional[str] = Field(default=None, max_length=128)
    max_tokens: Optional[int] = Field(default=None, ge=1, le=2048)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    stream: bool = False


class TokenUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    type: Literal["response"] = "response"
    message: str
    session_id: str
    model: str
    usage: TokenUsage
    latency_ms: float
    finish_reason: Optional[str] = None


class ErrorBody(BaseModel):
    type: Literal["error"] = "error"
    error: str
    detail: str
