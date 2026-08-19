from pathlib import Path

import pytest

from server.ai.llm import ChatTurn, LlamaCppEngine
from server.ai.prompts import JARVIS_SYSTEM_PROMPT
from server.config import REPO_ROOT, Settings

CANDIDATES = [
    REPO_ROOT / "models" / "llm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    REPO_ROOT / "models" / "llm" / "qwen2.5-0.5b-instruct-q4_k_m.gguf",
    REPO_ROOT / "models" / "llm" / "model.gguf",
]


def _first_gguf() -> Path | None:
    for path in CANDIDATES:
        if path.is_file() and path.stat().st_size > 10_000_000:
            return path
    llm_dir = REPO_ROOT / "models" / "llm"
    if llm_dir.is_dir():
        for path in sorted(llm_dir.glob("*.gguf")):
            if path.stat().st_size > 10_000_000:
                return path
    return None


def test_system_prompt_is_non_empty():
    assert "Jarvis" in JARVIS_SYSTEM_PROMPT
    assert "sir" in JARVIS_SYSTEM_PROMPT.lower()


def test_engine_prepends_system_prompt_when_missing():
    settings = Settings(llm_model_path="models/llm/missing.gguf")
    engine = LlamaCppEngine(settings)
    payload = engine._ensure_system_prompt([ChatTurn(role="user", content="Hello")])
    assert payload[0]["role"] == "system"
    assert "Jarvis" in payload[0]["content"]
    assert payload[1]["content"] == "Hello"
    engine.shutdown()


def test_engine_reports_missing_model(tmp_path):
    settings = Settings(llm_model_path=tmp_path / "nope.gguf")
    engine = LlamaCppEngine(settings)
    assert engine.model_file_present() is False
    assert engine.loaded is False
    assert engine.backend_name == "llama.cpp"
    engine.shutdown()


@pytest.mark.integration
def test_local_gguf_answers_without_cloud():
    model = _first_gguf()
    if model is None:
        pytest.skip(
            "No GGUF found under models/llm. Run: python scripts/download_model.py"
        )

    settings = Settings(
        llm_model_path=model,
        llm_n_ctx=512,
        llm_max_tokens=32,
        llm_temperature=0.1,
        llm_n_gpu_layers=0,
        llm_preload=False,
    )
    engine = LlamaCppEngine(settings)
    try:
        import asyncio

        result = asyncio.run(
            engine.chat(
                [ChatTurn(role="user", content="Reply with the single word: pong")],
                max_tokens=16,
                temperature=0.1,
                session_id="integration",
            )
        )
    finally:
        engine.shutdown()

    assert result.text, "local model returned empty text"
    assert result.latency_ms > 0
    assert model.name in result.model_path or result.model_path.endswith(".gguf")
    # The model should produce some tokens locally; do not require an exact string.
    assert result.completion_tokens >= 1 or len(result.text.split()) >= 1
