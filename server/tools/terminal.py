"""Safe subprocess argv for the local terminal tool. Never uses shell=True."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from server.tools.paths import ToolExecutionError

_META = re.compile(r"[|&;<>$`\\\n()]")
_ALLOW = {
    "git",
    "python",
    "python3",
    "ls",
    "whoami",
    "hostname",
    "date",
    "uname",
    "dir",
    "where",
    "ver",
}


def safe_argv(command: str) -> list[str]:
    text = (command or "").strip()
    if not text:
        raise ToolExecutionError("Command is empty.")
    if _META.search(text):
        raise ToolExecutionError("That command is not allowed.")
    try:
        parts = shlex.split(text, posix=os.name != "nt")
    except ValueError as exc:
        raise ToolExecutionError("I couldn't parse that command.") from exc
    if not parts:
        raise ToolExecutionError("Command is empty.")
    binary = Path(parts[0]).name
    if binary != parts[0] or "/" in parts[0] or "\\" in parts[0]:
        raise ToolExecutionError("That command is not allowed.")
    name = binary.lower()
    if name not in _ALLOW:
        raise ToolExecutionError("That command is not on the allowlist.")
    if name in {"python", "python3"} and any(
        arg == "-c" or arg == "-m" or arg.startswith("-c") for arg in parts[1:]
    ):
        raise ToolExecutionError("That command is not allowed.")
    if name == "dir" and os.name == "nt":
        return ["cmd", "/c", "dir", *parts[1:]]
    if name == "dir":
        return ["ls", *parts[1:]]
    if name == "ver" and os.name == "nt":
        return ["cmd", "/c", "ver"]
    return parts
