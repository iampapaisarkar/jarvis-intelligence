"""Local wake-word matching. Not a neural spotter; STT text is checked for 'Jarvis'."""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_WAKE_WORD = "jarvis"
DEFAULT_ALIASES = ("jarvis", "jarvish", "জার্ভিস")
_PREFIXES = ("hey", "hi", "ok", "okay", "oi")
_JUNK_TAGS = re.compile(r"^\[.+\]$", re.IGNORECASE)
_JUNK_PHRASES = {
    "blank",
    "blank audio",
    "(blank)",
    "silence",
    "you",
    "thank you",
    "thanks for watching",
}


@dataclass(frozen=True)
class WakeMatch:
    heard: bool
    word: str
    command: str
    transcript: str


def _aliases(word: str) -> tuple[str, ...]:
    cleaned = word.strip()
    names = [cleaned] if cleaned else [DEFAULT_WAKE_WORD]
    for extra in DEFAULT_ALIASES:
        if extra.casefold() not in {item.casefold() for item in names}:
            names.append(extra)
    return tuple(names)


def match_wake_word(text: str, *, word: str = DEFAULT_WAKE_WORD) -> WakeMatch:
    """True only when the wake word is at the start (optional hey/ok/oi prefix)."""
    transcript = " ".join((text or "").split())
    canonical = (word or DEFAULT_WAKE_WORD).strip() or DEFAULT_WAKE_WORD
    if not transcript:
        return WakeMatch(False, canonical, "", "")

    escaped = "|".join(re.escape(alias) for alias in _aliases(canonical))
    prefix = "|".join(re.escape(item) for item in _PREFIXES)
    pattern = re.compile(
        rf"^(?:(?:{prefix})\s+)?(?:{escaped})(?:\s*[,:;-]+\s*|\s+|$)",
        re.IGNORECASE,
    )
    matched = pattern.search(transcript)
    if matched is None:
        return WakeMatch(False, canonical, "", transcript)
    command = transcript[matched.end() :].strip(" ,:-")
    return WakeMatch(True, canonical, command, transcript)


def is_junk_transcript(text: str) -> bool:
    """Whisper often emits tags like [BLANK_AUDIO] for silence. Those are not commands."""
    cleaned = " ".join((text or "").split()).strip(" .!?")
    if not cleaned:
        return True
    if _JUNK_TAGS.match(cleaned):
        return True
    compact = cleaned.casefold().replace("_", " ")
    compact = compact.replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    return compact in _JUNK_PHRASES


def command_or_fallback(match: WakeMatch, *, fallback: bool) -> str:
    if match.heard:
        return match.command
    if fallback and not is_junk_transcript(match.transcript):
        return match.transcript
    return ""
