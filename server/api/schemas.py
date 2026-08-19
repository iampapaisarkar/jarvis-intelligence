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
    execution: Literal["disabled", "windows", "posix"] = "disabled"
    pending_confirmations: int = 0


class SafetyHealth(BaseModel):
    policy: Literal["local"] = "local"
    confirmation_ttl_seconds: int


class MacHealth(BaseModel):
    connected: bool = False
    hostname: Optional[str] = None
    version: Optional[str] = None


class MemoryHealth(BaseModel):
    ok: bool = False
    path: str = ""
    preferences: int = 0
    aliases: int = 0
    history: int = 0


class WakeHealth(BaseModel):
    enabled: bool = True
    word: str = "jarvis"
    backend: Literal["transcript"] = "transcript"


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    voice_ready: bool
    llm: LlmHealth
    stt: ModelHealth
    tts: ModelHealth
    tools: ToolsHealth
    safety: SafetyHealth
    mac: MacHealth = Field(default_factory=MacHealth)
    memory: MemoryHealth = Field(default_factory=MemoryHealth)
    wake: WakeHealth = Field(default_factory=WakeHealth)


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


class WakeDetectRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=128)
    fallback: bool = False


class WakeListenRequest(ListenRequest):
    fallback: bool = True


class WakeResponse(BaseModel):
    type: Literal["wake"] = "wake"
    heard: bool
    word: str
    command: str = ""
    transcript: str = ""
    session_id: str
    source: Literal["text", "upload", "microphone"] = "text"
    fallback_used: bool = False
    model: str = ""
    language: Optional[str] = None
    confidence: Optional[float] = None
    duration_ms: float = 0.0
    latency_ms: float = 0.0


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
    type: Literal["tool_call", "clarification", "reply", "confirmation_required", "denied"]
    executed: bool = False
    confirmed: bool = False
    safety: Literal["allowed", "needs_confirmation", "denied", "not_applicable"] = "not_applicable"
    message: str
    spoken_reply: str
    session_id: str
    tool: Optional[str] = None
    target: Optional[Literal["windows", "mac"]] = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: Optional[Literal["low", "medium", "high"]] = None
    requires_confirmation: Optional[bool] = None
    confirmation_id: Optional[str] = None
    reason: Optional[str] = None
    model: str = ""
    usage: TokenUsage
    latency_ms: float = 0.0
    parse_recovered: bool = False
    result: Optional[dict[str, Any]] = None


class ConfirmRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    confirmation_id: str = Field(min_length=8, max_length=128)
    approved: bool


class PendingQueryResponse(BaseModel):
    pending: bool
    session_id: str
    confirmation_id: Optional[str] = None
    tool: Optional[str] = None
    target: Optional[Literal["windows", "mac"]] = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: Optional[str] = None
    spoken_reply: Optional[str] = None
    expires_in_seconds: Optional[float] = None


class ToolListItem(BaseModel):
    name: str
    description: str
    targets: list[str]
    risk: str
    requires_confirmation: bool
    arguments: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class ToolListResponse(BaseModel):
    execution: Literal["disabled", "windows", "posix"] = "disabled"
    tools: list[ToolListItem]


class ErrorBody(BaseModel):
    type: Literal["error"] = "error"
    error: str
    detail: str
