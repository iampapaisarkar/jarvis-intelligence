"""Launch installed apps by canonical name. No downloaded executables."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Optional

from server.tools.catalog import resolve_application_alias
from server.tools.paths import ToolExecutionError

LaunchFn = Callable[[list[str]], None]

_WINDOWS_HINTS: dict[str, tuple[str, ...]] = {
    "notepad": ("notepad.exe",),
    "calculator": ("calc.exe",),
    "file explorer": ("explorer.exe",),
    "command prompt": ("cmd.exe",),
    "powershell": ("powershell.exe",),
    "visual studio code": (
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        r"%ProgramFiles%\Microsoft VS Code\Code.exe",
        r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe",
    ),
    "google chrome": (
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    ),
    "firefox": (
        r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
        r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
    ),
    "spotify": (r"%APPDATA%\Spotify\Spotify.exe",),
}


def _expand_win(path: str) -> Path:
    return Path(os.path.expandvars(path))


def windows_executable(application: str) -> Optional[Path]:
    canonical = resolve_application_alias(application)
    key = canonical.lower()
    for hint in _WINDOWS_HINTS.get(key, ()):
        candidate = _expand_win(hint)
        if candidate.is_file():
            return candidate
        found = shutil.which(hint)
        if found:
            return Path(found)
    which = shutil.which(canonical) or shutil.which(application)
    if which:
        return Path(which)
    return None


def app_argv(application: str, *, backend: str) -> list[str]:
    canonical = resolve_application_alias(application)
    if backend == "windows":
        exe = windows_executable(canonical)
        if exe is None:
            raise ToolExecutionError(f"I couldn't find {canonical} on this computer.")
        return [str(exe)]
    return ["open", "-a", canonical]


def launch_app(argv: list[str], launch: Optional[LaunchFn] = None) -> None:
    if launch is not None:
        launch(argv)
        return
    import subprocess

    subprocess.Popen(
        argv,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
