from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from server.ai.llm import ChatTurn, LLMResult
from server.config import clear_settings_cache
from server.dependencies import get_llm_engine, reset_singletons
from server.main import create_app
from server.utils.logger import reset_logging_for_tests


@dataclass
class FakeLLM:
    reply: str = "Sure, I can help with that."
    present: bool = True
    is_loaded: bool = False
    fail_with: Optional[Exception] = None
    last_messages: Optional[list[ChatTurn]] = None

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
    ) -> LLMResult:
        self.last_messages = messages
        self.is_loaded = True
        if self.fail_with is not None:
            raise self.fail_with
        return LLMResult(
            text=self.reply,
            model_path=self.model_path,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            latency_ms=12.3,
            finish_reason="stop",
        )


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LLM_MODEL_PATH", str(tmp_path / "missing.gguf"))
    monkeypatch.setenv("LLM_PRELOAD", "false")
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
def client(fake_llm: FakeLLM) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_llm_engine] = lambda: fake_llm
    with TestClient(app) as test_client:
        yield test_client
