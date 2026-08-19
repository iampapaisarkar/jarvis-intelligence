from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from server.config import Settings, get_settings


def tokens_match(provided: Optional[str], expected: str) -> bool:
    if provided is None:
        return False
    left = hashlib.sha256(provided.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


def extract_token(
    x_jarvis_token: Optional[str],
    authorization: Optional[str],
) -> Optional[str]:
    if x_jarvis_token:
        return x_jarvis_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def verify_auth_token(
    x_jarvis_token: Optional[str] = Header(default=None, alias="X-Jarvis-Token"),
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.auth_required:
        return
    token = extract_token(x_jarvis_token, authorization)
    if not tokens_match(token, settings.jarvis_auth_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication token",
        )
