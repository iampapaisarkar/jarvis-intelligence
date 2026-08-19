from __future__ import annotations

import re
from typing import Literal, Optional

Verdict = Literal["yes", "no", "other"]

_YES = {
    "yes",
    "y",
    "yeah",
    "yep",
    "yup",
    "ok",
    "okay",
    "confirm",
    "confirmed",
    "do it",
    "go ahead",
    "sure",
    "please do",
    "affirmative",
    "জি",
    "জি স্যার",
    "হ্যাঁ",
    "হ্যা",
    "ha",
    "haan",
    "haa",
}

_NO = {
    "no",
    "n",
    "nope",
    "nah",
    "cancel",
    "stop",
    "don't",
    "dont",
    "do not",
    "never",
    "abort",
    "না",
    "নাহ",
    "cancel that",
    "forget it",
}


def classify_confirmation(text: str) -> Verdict:
    cleaned = re.sub(r"[.!?]+$", "", (text or "").strip(), flags=re.UNICODE)
    cleaned = " ".join(cleaned.split())
    if not cleaned or len(cleaned) > 48:
        return "other"
    key = cleaned.lower()
    if cleaned in _YES or key in _YES:
        return "yes"
    if cleaned in _NO or key in _NO:
        return "no"
    return "other"
