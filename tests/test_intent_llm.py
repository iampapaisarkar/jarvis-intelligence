from pathlib import Path

import pytest

from server.ai.intent import IntentParser
from server.ai.llm import LlamaCppEngine
from server.config import REPO_ROOT, Settings
from server.tools.catalog import default_registry

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


@pytest.mark.integration
def test_local_gguf_plans_open_vscode_without_executing():
    model = _first_gguf()
    if model is None:
        pytest.skip("No GGUF found under models/llm. Run: python scripts/download_model.py")

    settings = Settings(
        llm_model_path=model,
        llm_n_ctx=1024,
        llm_n_gpu_layers=0,
        intent_max_tokens=128,
        intent_temperature=0.1,
        intent_json_retries=1,
        jarvis_default_target="windows",
    )
    engine = LlamaCppEngine(settings)
    parser = IntentParser(engine, default_registry(), settings)
    try:
        import asyncio

        parsed = asyncio.run(
            parser.parse(
                "Open Visual Studio Code on my Mac.",
                session_id="phase4-integration",
                default_target="mac",
            )
        )
    finally:
        engine.shutdown()

    assert parsed.executed is False
    assert parsed.type == "tool_call"
    assert parsed.tool == "open_application"
    assert "visual studio" in parsed.arguments["application"].lower()
    assert parsed.target == "mac"
    assert parsed.risk == "low"
