from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ModelHealth(BaseModel):
    backend: str
    model_path: str
    model_file_present: bool
    model_loaded: bool


class LlmHealth(ModelHealth):
    n_ctx: int
    n_gpu_layers: int


class ToolsHealth(BaseModel):
    registered: int
    execution: Literal["disabled"] = "disabled"


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    voice_ready: bool
    llm: LlmHealth
    stt: ModelHealth
    tts: ModelHealth
    tools: ToolsHealth


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


class TranscriptSegmentOut(BaseModel):
    text: str
    start_ms: float = 0.0
    end_ms: float = 0.0
    confidence: Optional[float] = None


class TranscriptResponse(BaseModel):
    type: Literal["transcript"] = "transcript"
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    segments: list[TranscriptSegmentOut] = Field(default_factory=list)
    duration_ms: float = 0.0
    latency_ms: float = 0.0
    model: str
    session_id: str
    source: Literal["upload", "microphone"] = "upload"


class ListenRequest(BaseModel):
    duration_seconds: float = Field(default=5.0, ge=1.0, le=20.0)
    language: Optional[str] = Field(default=None, max_length=16)
    session_id: Optional[str] = Field(default=None, max_length=128)


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    language: Optional[str] = Field(default=None, max_length=16)
    session_id: Optional[str] = Field(default=None, max_length=128)
    play: bool = False


class IntentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=128)
    target: Optional[Literal["windows", "mac"]] = None


class IntentResponse(BaseModel):
    type: Literal["tool_call", "clarification", "reply"]
    executed: bool = False
    message: str
    spoken_reply: str
    session_id: str
    tool: Optional[str] = None
    target: Optional[Literal["windows", "mac"]] = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: Optional[Literal["low", "medium", "high"]] = None
    requires_confirmation: Optional[bool] = None
    model: str = ""
    usage: TokenUsage
    latency_ms: float = 0.0
    parse_recovered: bool = False


class ToolListItem(BaseModel):
    name: str
    description: str
    targets: list[str]
    risk: str
    requires_confirmation: bool
    arguments: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ToolListResponse(BaseModel):
    execution: Literal["disabled"] = "disabled"
    tools: list[ToolListItem]


class ErrorBody(BaseModel):
    type: Literal["error"] = "error"
    error: str
    detail: str
