from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from server.ai.llm import ChatTurn, LLMResult
from server.ai.stt import Transcript, TranscriptSegment
from server.ai.tts import SynthesizedSpeech
from server.config import clear_settings_cache
from server.dependencies import get_llm_engine, get_stt_engine, get_tool_executor, get_tts_engine, reset_singletons
from server.main import create_app
from server.utils.logger import reset_logging_for_tests


@dataclass
class FakeLLM:
    reply: str = "Sure, I can help with that."
    present: bool = True
    is_loaded: bool = False
    fail_with: Optional[Exception] = None
    last_messages: Optional[list[ChatTurn]] = None
    last_json_mode: bool = False
    replies: Optional[list[str]] = None
    call_count: int = 0

    backend_name: str = "fake"
    model_path: str = "/tmp/fake-model.gguf"

    @property
    def loaded(self) -> bool:
        return self.is_loaded

    def model_file_present(self) -> bool:
        return self.present

    def load(self) -> None:
        self.is_loaded = True

    def unload(self) -> None:
        self.is_loaded = False

    def shutdown(self) -> None:
        self.unload()

    async def chat(
        self,
        messages: list[ChatTurn],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        session_id: str = "-",
        json_mode: bool = False,
    ) -> LLMResult:
        self.last_messages = messages
        self.last_json_mode = json_mode
        self.is_loaded = True
        if self.fail_with is not None:
            raise self.fail_with
        text = self.reply
        if self.replies:
            text = self.replies[min(self.call_count, len(self.replies) - 1)]
        self.call_count += 1
        return LLMResult(
            text=text,
            model_path=self.model_path,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=12.3,
            finish_reason="stop",
        )


@dataclass
class FakeSTT:
    reply: str = "open visual studio code"
    present: bool = True
    is_loaded: bool = False
    fail_with: Optional[Exception] = None
    last_path: Optional[Path] = None
    last_language: Optional[str] = None
    confidence: Optional[float] = 0.91
    backend_name: str = "fake-whisper"
    model_path: str = "/tmp/fake-whisper.bin"

    @property
    def loaded(self) -> bool:
        return self.is_loaded

    def model_file_present(self) -> bool:
        return self.present

    def load(self) -> None:
        self.is_loaded = True

    def unload(self) -> None:
        self.is_loaded = False

    def shutdown(self) -> None:
        self.unload()

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: Optional[str] = None,
        session_id: str = "-",
    ) -> Transcript:
        self.last_path = audio_path
        self.last_language = language
        self.is_loaded = True
        if self.fail_with is not None:
            raise self.fail_with
        return Transcript(
            text=self.reply,
            language=language or "en",
            confidence=self.confidence,
            segments=[
                TranscriptSegment(text=self.reply, start_ms=0, end_ms=1200, confidence=self.confidence)
            ],
            duration_ms=1200,
            latency_ms=40.0,
            model_path=self.model_path,
        )


@dataclass
class FakeTTS:
    present: bool = True
    is_loaded: bool = False
    fail_with: Optional[Exception] = None
    last_text: Optional[str] = None
    last_language: Optional[str] = None
    last_play: bool = False
    backend_name: str = "fake-piper"
    model_path: str = "/tmp/fake-piper.onnx"

    @property
    def loaded(self) -> bool:
        return self.is_loaded

    def model_file_present(self) -> bool:
        return self.present

    def load(self) -> None:
        self.is_loaded = True

    def unload(self) -> None:
        self.is_loaded = False

    def shutdown(self) -> None:
        self.unload()

    async def speak(
        self,
        text: str,
        language: Optional[str] = None,
        *,
        dest: Path,
        play: bool = False,
        session_id: str = "-",
    ) -> SynthesizedSpeech:
        self.last_text = text
        self.last_language = language
        self.last_play = play
        self.is_loaded = True
        if self.fail_with is not None:
            raise self.fail_with
        import numpy as np

        from server.utils.audio import write_wav_mono16k

        write_wav_mono16k(dest, np.zeros(1600, dtype=np.int16), 16000)
        return SynthesizedSpeech(
            path=dest,
            text=text,
            language=language or "en",
            voice="fake",
            backend=self.backend_name,
            sample_rate=16000,
            duration_ms=100.0,
            latency_ms=8.0,
            fallback=False,
        )


@dataclass
class RecordingLauncher:
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, argv: list[str]) -> None:
        self.calls.append(list(argv))


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("JARVIS_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LLM_MODEL_PATH", str(tmp_path / "missing.gguf"))
    monkeypatch.setenv("STT_MODEL_PATH", str(tmp_path / "missing-whisper.bin"))
    monkeypatch.setenv("TTS_MODEL_PATH", str(tmp_path / "missing-piper.onnx"))
    monkeypatch.setenv("LLM_PRELOAD", "false")
    monkeypatch.setenv("STT_PRELOAD", "false")
    monkeypatch.setenv("TTS_PRELOAD", "false")
    monkeypatch.setenv("JARVIS_TOOLS_ENABLED", "true")
    monkeypatch.setenv("JARVIS_TOOLS_BACKEND", "posix")
    monkeypatch.setenv("JARVIS_WORKSPACE", str(workspace))
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    clear_settings_cache()
    reset_singletons()
    reset_logging_for_tests()
    yield
    clear_settings_cache()
    reset_singletons()


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_stt() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
def fake_tts() -> FakeTTS:
    return FakeTTS()


@pytest.fixture
def app_launcher() -> RecordingLauncher:
    return RecordingLauncher()


@pytest.fixture
def client(
    fake_llm: FakeLLM, fake_stt: FakeSTT, fake_tts: FakeTTS, app_launcher: RecordingLauncher
) -> TestClient:
    from server.config import get_settings
    from server.tools.executor import LocalToolExecutor

    app = create_app()
    app.dependency_overrides[get_llm_engine] = lambda: fake_llm
    app.dependency_overrides[get_stt_engine] = lambda: fake_stt
    app.dependency_overrides[get_tts_engine] = lambda: fake_tts
    app.dependency_overrides[get_tool_executor] = lambda: LocalToolExecutor(
        get_settings(), launch=app_launcher
    )
    with TestClient(app) as test_client:
        yield test_client
