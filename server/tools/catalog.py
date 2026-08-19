"""Built-in tool schemas. No OS side effects in Phase 4."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

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
}


def resolve_application_alias(name: str) -> str:
    key = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
    return APPLICATION_ALIASES.get(key, name.strip())


class OpenApplicationArgs(BaseModel):
    application: str = Field(min_length=1, max_length=128)

    @field_validator("application")
    @classmethod
    def _canonical(cls, value: str) -> str:
        resolved = resolve_application_alias(value)
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


OPEN_APPLICATION = ToolSpec(
    name="open_application",
    description="Open an installed application by canonical name.",
    allowed_targets=("windows", "mac"),
    risk="low",
    requires_confirmation=False,
    args_model=OpenApplicationArgs,
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

DEFAULT_TOOLS = (
    OPEN_APPLICATION,
    LIST_DIRECTORY,
    GET_SYSTEM_INFO,
    CREATE_FOLDER,
    CREATE_FILE,
)


def default_registry() -> ToolRegistry:
    return ToolRegistry(DEFAULT_TOOLS)
