"""SQLite-backed preferences, aliases, and recent tasks. Stdlib only."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from server.memory.keys import (
    ALLOWED_PREFERENCE_KEYS,
    ALIAS_KINDS,
    DEFAULT_PATH_ALIASES,
    DEFAULT_PROJECTS_DIRECTORY,
)
from server.utils.logger import get_logger

logger = get_logger("jarvis.memory")

SCHEMA_VERSION = 1

_CREATE = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aliases (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool TEXT,
    target TEXT,
    arguments_json TEXT,
    spoken TEXT,
    reason TEXT,
    executed INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MemoryStore:
    def __init__(self, path: Path, *, history_limit: int = 200) -> None:
        self.path = path
        self._history_limit = max(20, min(history_limit, 2000))
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._seed()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            prefs = self._conn.execute("SELECT COUNT(*) FROM preferences").fetchone()[0]
            aliases = self._conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
            history = self._conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        return {
            "ok": True,
            "path": str(self.path),
            "preferences": int(prefs),
            "aliases": int(aliases),
            "history": int(history),
        }

    def get_preference(self, key: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
        return None if row is None else str(row["value"])

    def list_preferences(self) -> list[dict[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value, updated_at FROM preferences ORDER BY key"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_preference(self, key: str, value: str) -> dict[str, str]:
        cleaned_key = key.strip().lower()
        if cleaned_key not in ALLOWED_PREFERENCE_KEYS:
            raise ValueError(f"Unknown preference key: {key}")
        cleaned_value = value.strip()
        if not cleaned_value or len(cleaned_value) > 512:
            raise ValueError("Preference value must be 1–512 characters")
        stamp = _now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO preferences(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (cleaned_key, cleaned_value, stamp),
            )
            self._conn.commit()
        logger.info("memory preference key=%s", cleaned_key)
        return {"key": cleaned_key, "value": cleaned_value, "updated_at": stamp}

    def delete_preference(self, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM preferences WHERE key = ?", (key.strip().lower(),))
            self._conn.commit()
            return cur.rowcount > 0

    def list_aliases(self, *, kind: Optional[str] = None) -> list[dict[str, str]]:
        with self._lock:
            if kind:
                rows = self._conn.execute(
                    "SELECT name, kind, value, updated_at FROM aliases WHERE kind = ? ORDER BY name",
                    (kind,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT name, kind, value, updated_at FROM aliases ORDER BY kind, name"
                ).fetchall()
        return [dict(row) for row in rows]

    def set_alias(self, name: str, kind: str, value: str) -> dict[str, str]:
        cleaned_kind = kind.strip().lower()
        if cleaned_kind not in ALIAS_KINDS:
            raise ValueError("Alias kind must be application or path")
        cleaned_name = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
        cleaned_value = value.strip()
        if not cleaned_name or not cleaned_value or len(cleaned_name) > 128 or len(cleaned_value) > 512:
            raise ValueError("Alias name/value is invalid")
        stamp = _now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO aliases(name, kind, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET kind = excluded.kind, value = excluded.value, updated_at = excluded.updated_at
                """,
                (cleaned_name, cleaned_kind, cleaned_value, stamp),
            )
            self._conn.commit()
        return {
            "name": cleaned_name,
            "kind": cleaned_kind,
            "value": cleaned_value,
            "updated_at": stamp,
        }

    def delete_alias(self, name: str) -> bool:
        key = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
        with self._lock:
            cur = self._conn.execute("DELETE FROM aliases WHERE name = ?", (key,))
            self._conn.commit()
            return cur.rowcount > 0

    def resolve_application(self, name: str) -> Optional[str]:
        key = " ".join((name or "").strip().lower().replace("_", " ").replace("-", " ").split())
        if not key:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM aliases WHERE name = ? AND kind = 'application'",
                (key,),
            ).fetchone()
        return None if row is None else str(row["value"])

    def resolve_path(self, path: str, *, join_projects: bool) -> str:
        cleaned = (path or "").strip()
        if not cleaned:
            return cleaned
        key = " ".join(cleaned.lower().replace("_", " ").replace("-", " ").split())
        with self._lock:
            alias = self._conn.execute(
                "SELECT value FROM aliases WHERE name = ? AND kind = 'path'",
                (key,),
            ).fetchone()
        if alias is not None:
            return str(alias["value"])
        if join_projects and _is_bare_name(cleaned):
            root = self.get_preference("default_projects_directory") or DEFAULT_PROJECTS_DIRECTORY
            return f"{root.rstrip('/')}/{cleaned}"
        return cleaned

    def list_history(self, *, limit: int = 20) -> list[dict[str, Any]]:
        cap = max(1, min(limit, 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, session_id, tool, target, arguments_json, spoken, reason, executed, created_at
                FROM history ORDER BY id DESC LIMIT ?
                """,
                (cap,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            raw = item.pop("arguments_json")
            try:
                item["arguments"] = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                item["arguments"] = {}
            item["executed"] = bool(item["executed"])
            items.append(item)
        return items

    def record_task(
        self,
        *,
        session_id: str,
        tool: Optional[str],
        target: Optional[str],
        arguments: Optional[dict[str, Any]],
        spoken: str,
        reason: Optional[str],
        executed: bool,
    ) -> None:
        payload = json.dumps(arguments or {}, ensure_ascii=False)[:800]
        stamp = _now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO history(session_id, tool, target, arguments_json, spoken, reason, executed, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    tool,
                    target,
                    payload,
                    (spoken or "")[:400],
                    reason,
                    1 if executed else 0,
                    stamp,
                ),
            )
            self._conn.execute(
                """
                DELETE FROM history WHERE id NOT IN (
                    SELECT id FROM history ORDER BY id DESC LIMIT ?
                )
                """,
                (self._history_limit,),
            )
            self._conn.commit()

    def apply_remember(self, arguments: dict[str, Any]) -> tuple[bool, str, str, dict[str, Any]]:
        try:
            saved = self.set_preference(str(arguments.get("key") or ""), str(arguments.get("value") or ""))
        except ValueError as exc:
            return False, str(exc), "invalid_preference", {}
        key = saved["key"]
        spoken = (
            f"I'll remember that your projects are in {saved['value']}."
            if key == "default_projects_directory"
            else f"I'll remember {key}."
        )
        return True, spoken, "remembered", saved

    def prompt_context(self) -> str:
        prefs = self.list_preferences()
        aliases = self.list_aliases()[:16]
        if not prefs and not aliases:
            return ""
        lines = ["Memory (use if relevant; do not invent other facts):"]
        for item in prefs:
            lines.append(f"- preference {item['key']} = {item['value']}")
        for item in aliases:
            lines.append(f"- {item['kind']} alias {item['name']} = {item['value']}")
        lines.append(
            "If the user states a lasting preference, use remember_preference. "
            "A folder name with no path uses default_projects_directory as the parent."
        )
        return "\n".join(lines)

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_CREATE)
            row = self._conn.execute("SELECT version FROM schema_meta").fetchone()
            if row is None:
                self._conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
            self._conn.commit()

    def _seed(self) -> None:
        if self.get_preference("default_projects_directory") is None:
            self.set_preference("default_projects_directory", DEFAULT_PROJECTS_DIRECTORY)
        with self._lock:
            existing = {
                str(row["name"])
                for row in self._conn.execute("SELECT name FROM aliases WHERE kind = 'path'").fetchall()
            }
        for name, value in DEFAULT_PATH_ALIASES:
            if name not in existing:
                self.set_alias(name, "path", value)


def _is_bare_name(path: str) -> bool:
    cleaned = path.strip()
    if not cleaned or cleaned.startswith("~") or cleaned.startswith("/") or cleaned.startswith("\\"):
        return False
    if len(cleaned) >= 2 and cleaned[1] == ":":
        return False
    return "/" not in cleaned and "\\" not in cleaned
