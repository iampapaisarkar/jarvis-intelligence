from server.config import REPO_ROOT, Settings, get_settings
from server.utils.logger import redact
from server.utils.security import extract_token, tokens_match


def test_relative_model_path_resolves_under_repo_root():
    settings = Settings(llm_model_path="models/llm/demo.gguf")
    resolved = settings.model_file
    assert resolved == (REPO_ROOT / "models" / "llm" / "demo.gguf").resolve()
    assert resolved.is_absolute()


def test_empty_n_threads_env_is_ignored(monkeypatch):
    monkeypatch.setenv("LLM_N_THREADS", "")
    from server.config import clear_settings_cache

    clear_settings_cache()
    assert get_settings().llm_n_threads is None


def test_auth_required_when_token_set(monkeypatch):
    monkeypatch.setenv("JARVIS_AUTH_TOKEN", "secret-value")
    from server.config import clear_settings_cache

    clear_settings_cache()
    assert get_settings().auth_required is True
    assert get_settings().jarvis_auth_token == "secret-value"


def test_invalid_log_level_rejected():
    try:
        Settings(log_level="VERBOSE")
        assert False, "expected validation error"
    except Exception as exc:
        assert "LOG_LEVEL" in str(exc)


def test_redact_removes_tokens_from_dicts():
    payload = {"user": "papai", "token": "abc123", "nested": {"api_key": "xyz"}}
    redacted = redact(payload)
    assert redacted["token"] == "[redacted]"
    assert redacted["nested"]["api_key"] == "[redacted]"
    assert redacted["user"] == "papai"


def test_tokens_match_accepts_only_exact_value():
    assert tokens_match("test-token", "test-token") is True
    assert tokens_match("other", "test-token") is False
    assert tokens_match(None, "test-token") is False


def test_extract_token_prefers_x_jarvis_header():
    assert extract_token("from-header", "Bearer other") == "from-header"
    assert extract_token(None, "Bearer abc") == "abc"
    assert extract_token(None, "Basic abc") is None
