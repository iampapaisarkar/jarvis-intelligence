"""Build browser URLs for spoken web requests. Only http(s) is allowed."""

from __future__ import annotations

from urllib.parse import quote_plus, urlparse

from server.safety.policy import url_is_allowed
from server.tools.paths import ToolExecutionError


def youtube_search_url(query: str) -> str:
    cleaned = " ".join((query or "").strip().split())
    if not cleaned:
        raise ToolExecutionError("I need something to search on YouTube.")
    return "https://www.youtube.com/results?search_query=" + quote_plus(cleaned)


def google_search_url(query: str) -> str:
    cleaned = " ".join((query or "").strip().split())
    if not cleaned:
        raise ToolExecutionError("I need something to search.")
    return "https://www.google.com/search?q=" + quote_plus(cleaned)


def require_allowed_url(url: str) -> str:
    cleaned = (url or "").strip()
    if not url_is_allowed(cleaned):
        raise ToolExecutionError("I can only open a normal web page.")
    parsed = urlparse(cleaned)
    return parsed.geturl() if parsed.scheme else cleaned


def url_argv(url: str, *, backend: str) -> list[str]:
    require_allowed_url(url)
    if backend == "windows":
        return ["cmd", "/c", "start", "", url]
    return ["open", url]
