"""In-memory pending confirmations, bound to session_id."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from server.tools.base import Target


@dataclass
class PendingAction:
    confirmation_id: str
    session_id: str
    tool: str
    target: Target
    arguments: dict[str, Any]
    risk: str
    spoken_summary: str
    created_at: float
    expires_at: float
    extra: dict[str, Any] = field(default_factory=dict)

    def expired(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) >= self.expires_at


class ConfirmationStore:
    def __init__(self, ttl_seconds: int = 120) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._by_session: dict[str, PendingAction] = {}

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def pending_count(self) -> int:
        self.expire()
        with self._lock:
            return len(self._by_session)

    def expire(self, now: Optional[float] = None) -> None:
        stamp = now or time.time()
        with self._lock:
            dead = [sid for sid, item in self._by_session.items() if item.expired(stamp)]
            for sid in dead:
                del self._by_session[sid]

    def put(
        self,
        *,
        session_id: str,
        tool: str,
        target: Target,
        arguments: dict[str, Any],
        risk: str,
        spoken_summary: str,
        extra: Optional[dict[str, Any]] = None,
    ) -> PendingAction:
        now = time.time()
        action = PendingAction(
            confirmation_id=secrets.token_urlsafe(16),
            session_id=session_id,
            tool=tool,
            target=target,
            arguments=dict(arguments),
            risk=risk,
            spoken_summary=spoken_summary,
            created_at=now,
            expires_at=now + self._ttl,
            extra=dict(extra or {}),
        )
        with self._lock:
            self._by_session[session_id] = action
        return action

    def get_for_session(self, session_id: str) -> Optional[PendingAction]:
        self.expire()
        with self._lock:
            return self._by_session.get(session_id)

    def get(self, session_id: str, confirmation_id: str) -> Optional[PendingAction]:
        pending = self.get_for_session(session_id)
        if pending is None or pending.confirmation_id != confirmation_id:
            return None
        return pending

    def pop(self, session_id: str, confirmation_id: str) -> Optional[PendingAction]:
        self.expire()
        with self._lock:
            pending = self._by_session.get(session_id)
            if pending is None or pending.confirmation_id != confirmation_id:
                return None
            del self._by_session[session_id]
            return pending

    def cancel_session(self, session_id: str) -> Optional[PendingAction]:
        with self._lock:
            return self._by_session.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._by_session.clear()
