"""Resolve user paths and keep filesystem tools inside allowed roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from server.config import Settings
from server.safety.policy import is_system_path
from server.tools.base import Target, ToolError


class ToolExecutionError(ToolError):
    pass


def user_home() -> Path:
    return Path.home().expanduser().resolve()


def workspace_root(settings: Settings) -> Optional[Path]:
    if not settings.jarvis_workspace:
        return None
    path = settings.resolve_path(settings.jarvis_workspace)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def allowed_roots(settings: Settings) -> list[Path]:
    roots = [user_home()]
    workspace = workspace_root(settings)
    if workspace is not None and workspace not in roots:
        roots.append(workspace)
    return roots


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_user_path(
    path: str,
    settings: Settings,
    *,
    target: Target,
    must_exist: bool = False,
    destructive: bool = True,
) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        base = workspace_root(settings) or user_home()
        raw = base / raw
    absolute = Path(os.path.abspath(raw))
    if absolute.parent.exists():
        absolute = absolute.parent.resolve() / absolute.name
    if must_exist:
        if not absolute.exists():
            raise ToolExecutionError("I couldn't find that path.")
        absolute = absolute.resolve()
    if is_system_path(str(absolute), target, destructive=destructive):
        raise ToolExecutionError("That path is blocked by safety policy.")
    if not any(_is_under(absolute, root) for root in allowed_roots(settings)):
        raise ToolExecutionError("That path is outside the allowed folders.")
    home = user_home()
    workspace = workspace_root(settings)
    if destructive and (absolute == home or (workspace is not None and absolute == workspace)):
        raise ToolExecutionError("I won't delete the home or workspace folder.")
    return absolute
