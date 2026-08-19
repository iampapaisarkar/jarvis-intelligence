"""Built-in tool schemas. No OS side effects in Phase 4."""

from __future__ import annotations

import re

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from server.memory.keys import ALLOWED_PREFERENCE_KEYS
from server.tools.base import ToolSpec
from server.tools.registry import ToolRegistry

APPLICATION_ALIASES = {
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vs-code": "Visual Studio Code",
    "vsc": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "google chrome": "Google Chrome",
    "chrome": "Google Chrome",
    "safari": "Safari",
    "firefox": "Firefox",
    "finder": "Finder",
    "explorer": "File Explorer",
    "file explorer": "File Explorer",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "cmd": "Command Prompt",
    "command prompt": "Command Prompt",
    "powershell": "PowerShell",
    "notepad": "Notepad",
    "notes": "Notes",
    "calculator": "Calculator",
    "spotify": "Spotify",
    "slack": "Slack",
    "zoom": "zoom.us",
    "discord": "Discord",
    "whatsapp": "WhatsApp",
    "notion": "Notion",
    "cursor": "Cursor",
    "mail": "Mail",
    "messages": "Messages",
    "photos": "Photos",
    "music": "Music",
    "maps": "Maps",
    "facetime": "FaceTime",
    "calendar": "Calendar",
    "reminders": "Reminders",
    "preview": "Preview",
    "textedit": "TextEdit",
    "text edit": "TextEdit",
    "xcode": "Xcode",
    "figma": "Figma",
    "postman": "Postman",
    "docker": "Docker",
    "telegram": "Telegram",
    "signal": "Signal",
    "brave": "Brave Browser",
    "arc": "Arc",
    "system settings": "System Settings",
    "settings": "System Settings",
    "app store": "App Store",
}


_APP_SMALL_WORDS = frozenset({"and", "of", "the", "for"})

PROJECT_KIND_ALIASES = {
    "node": "node",
    "nodejs": "node",
    "node js": "node",
    "not just": "node",
    "no js": "node",
    "javascript": "node",
    "js": "node",
    "python": "python",
    "django": "python",
    "flask": "python",
    "react": "react",
    "reactjs": "react",
    "react js": "react",
    "next": "next",
    "nextjs": "next",
    "next js": "next",
    "vue": "vue",
    "vuejs": "vue",
    "vue js": "vue",
    "html": "html",
    "website": "html",
    "web": "html",
    "web app": "html",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "java": "java",
    "typescript": "typescript",
    "type script": "typescript",
    "ts": "typescript",
    "angular": "angular",
}


def resolve_application_alias(name: str) -> str:
    key = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
    return APPLICATION_ALIASES.get(key, name.strip())


def canonical_application_name(name: str) -> str:
    stripped = (name or "").strip()
    if not stripped:
        return stripped
    aliased = resolve_application_alias(stripped)
    if is_known_application(stripped):
        return aliased
    parts = stripped.split()
    titled: list[str] = []
    for index, part in enumerate(parts):
        low = part.lower()
        if index > 0 and low in _APP_SMALL_WORDS:
            titled.append(low)
        else:
            titled.append(part[:1].upper() + part[1:] if part else part)
    return " ".join(titled)


def normalize_project_kind(value: str) -> str:
    key = re.sub(r"[.\-]+", " ", (value or "").strip().lower())
    key = " ".join(key.split())
    if key in PROJECT_KIND_ALIASES:
        return PROJECT_KIND_ALIASES[key]
    compact = re.sub(r"[^a-z0-9]+", "", key)
    return PROJECT_KIND_ALIASES.get(compact, "generic")


def is_known_application(name: str) -> bool:
    key = " ".join((name or "").strip().lower().replace("_", " ").replace("-", " ").split())
    if not key:
        return False
    if key in APPLICATION_ALIASES:
        return True
    return key in {value.lower() for value in APPLICATION_ALIASES.values()}


class OpenApplicationArgs(BaseModel):
    application: str = Field(min_length=1, max_length=128)

    @field_validator("application")
    @classmethod
    def _canonical(cls, value: str) -> str:
        resolved = canonical_application_name(value)
        if not resolved:
            raise ValueError("application name is required")
        return resolved


class PathArgs(BaseModel):
    path: str = Field(min_length=1, max_length=512)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "\x00" in cleaned:
            raise ValueError("path must be a non-empty string")
        return cleaned


class CreateFileArgs(PathArgs):
    content: str = Field(default="", max_length=8000)


class EmptyArgs(BaseModel):
    pass


class OpenPathArgs(PathArgs):
    application: Optional[str] = Field(default=None, max_length=128)

    @field_validator("application")
    @classmethod
    def _open_with(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        return resolve_application_alias(value)


def slugify_project_name(value: str) -> str:
    cleaned = " ".join((value or "").strip().lower().split())
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return (cleaned or "app")[:64]


class OpenUrlArgs(BaseModel):
    url: str = Field(min_length=8, max_length=2048)

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        from server.safety.policy import url_is_allowed

        cleaned = value.strip()
        if not url_is_allowed(cleaned):
            raise ValueError("url must be a normal http or https page")
        return cleaned


class CreateProjectArgs(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="node", min_length=1, max_length=32)
    open_in: Optional[str] = Field(default="Visual Studio Code", max_length=128)
    path: Optional[str] = Field(default=None, max_length=512)

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        return normalize_project_kind(value)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        slug = slugify_project_name(value)
        if not slug:
            raise ValueError("project name is required")
        return slug

    @field_validator("path")
    @classmethod
    def _path(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        cleaned = value.strip()
        if "\x00" in cleaned:
            raise ValueError("path must be a non-empty string")
        return cleaned

    @field_validator("open_in")
    @classmethod
    def _editor(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not str(value).strip():
            return None
        return resolve_application_alias(value)


class RememberPreferenceArgs(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=512)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in ALLOWED_PREFERENCE_KEYS:
            raise ValueError("unknown preference key")
        return cleaned

    @field_validator("value")
    @classmethod
    def _value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value is required")
        return cleaned


class RunTerminalArgs(BaseModel):
    command: str = Field(min_length=1, max_length=500)

    @field_validator("command")
    @classmethod
    def _command(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("command is required")
        return cleaned


OPEN_APPLICATION = ToolSpec(
    name="open_application",
    description="Open any installed application by name. Unknown names are tried as written.",
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=OpenApplicationArgs,
)

OPEN_PATH = ToolSpec(
    name="open_path",
    description="Open a file or project folder. Optional application (e.g. Visual Studio Code) opens it in that app.",
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=OpenPathArgs,
)

OPEN_URL = ToolSpec(
    name="open_url",
    description="Open an http(s) page in the default browser. Use for YouTube, Google search, or a normal website.",
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=OpenUrlArgs,
)

LIST_DIRECTORY = ToolSpec(
    name="list_directory",
    description="List files and folders at a path. Do not use if the path is unknown.",
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=PathArgs,
)

GET_SYSTEM_INFO = ToolSpec(
    name="get_system_info",
    description="Report basic OS, CPU, and memory information for the target machine.",
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=EmptyArgs,
)

CREATE_PROJECT = ToolSpec(
    name="create_project",
    description=(
        "Scaffold a starter project under the projects folder and optionally open it in VS Code. "
        "kind: node, python, react, next, vue, html, go, rust, java, typescript, angular, or generic."
    ),
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=CreateProjectArgs,
)

CREATE_FOLDER = ToolSpec(
    name="create_folder",
    description="Create a folder at the given path. Ask a clarifying question if the path is missing.",
    allowed_targets=("windows", "mac"),
    risk="medium",
    requires_confirmation=True,
    args_model=PathArgs,
)

CREATE_FILE = ToolSpec(
    name="create_file",
    description="Create or overwrite a text file. Ask if the path is missing.",
    allowed_targets=("windows", "mac"),
    risk="medium",
    requires_confirmation=True,
    args_model=CreateFileArgs,
)

DELETE_PATH = ToolSpec(
    name="delete_path",
    description="Delete a file or folder. Always needs confirmation. System paths are blocked.",
    allowed_targets=("windows", "mac"),
    risk="high",
    requires_confirmation=True,
    args_model=PathArgs,
)

RUN_TERMINAL = ToolSpec(
    name="run_terminal",
    description="Run one shell command. Dangerous commands are blocked. Always needs confirmation.",
    allowed_targets=("windows", "mac"),
    risk="high",
    requires_confirmation=True,
    args_model=RunTerminalArgs,
)

REMEMBER_PREFERENCE = ToolSpec(
    name="remember_preference",
    description=(
        "Store a lasting personal fact or preference. Allowed keys: "
        "owner_name, owner_email, owner_phone, owner_address, spouse_name, child_name, "
        "preferred_language, address_as, default_projects_directory."
    ),
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=RememberPreferenceArgs,
)

DEFAULT_TOOLS = (
    OPEN_APPLICATION,
    OPEN_PATH,
    OPEN_URL,
    CREATE_PROJECT,
    LIST_DIRECTORY,
    GET_SYSTEM_INFO,
    CREATE_FOLDER,
    CREATE_FILE,
    DELETE_PATH,
    RUN_TERMINAL,
    REMEMBER_PREFERENCE,
)


def default_registry() -> ToolRegistry:
    return ToolRegistry(DEFAULT_TOOLS)
