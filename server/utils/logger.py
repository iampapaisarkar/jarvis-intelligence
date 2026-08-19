from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from server.config import Settings

_SECRET_KEYS = {
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "credential",
    "credentials",
    "jarvis_auth_token",
}

_TOKEN_RE = re.compile(
    r"(?i)(token|password|api[_-]?key|secret|bearer)\s*[:=]\s*\S+"
)

_configured = False


def redact(value: Any) -> Any:
    """Strip secrets from structures that may be logged."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return type(value)(redact(item) for item in value)
    if isinstance(value, str):
        return _TOKEN_RE.sub(r"\1=[redacted]", value)
    return value


class SessionIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "session_id"):
            record.session_id = "-"
        return True


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = redact(record.args)
        elif isinstance(record.args, tuple):
            record.args = tuple(redact(arg) for arg in record.args)
        if isinstance(record.msg, str):
            record.msg = _TOKEN_RE.sub(r"\1=[redacted]", record.msg)
        return True


def setup_logging(settings: Settings) -> None:
    global _configured
    if _configured:
        return

    log_dir: Path = settings.log_directory
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "jarvis.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s session=%(session_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers.clear()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(SessionIdFilter())
    stream.addFilter(RedactingFilter())

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SessionIdFilter())
    file_handler.addFilter(RedactingFilter())

    root.addHandler(stream)
    root.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True


def reset_logging_for_tests() -> None:
    global _configured
    _configured = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
