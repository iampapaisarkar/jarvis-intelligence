"""Run allowed tools on the local machine after safety has approved them."""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from server.config import Settings
from server.memory.keys import BRAIN_LOCAL_TOOLS
from server.safety.engine import GatedIntent
from server.safety.policy import command_is_forbidden
from server.tools.apps import LaunchFn, app_argv, launch_app, path_argv
from server.tools.base import Target, ToolSpec
from server.tools.paths import ToolExecutionError, resolve_user_path, user_home, workspace_root
from server.tools.registry import ToolRegistry
from server.tools.terminal import safe_argv
from server.utils.logger import get_logger

logger = get_logger("jarvis.tools")

_LIST_LIMIT = 40
_OUTPUT_LIMIT = 4000


@dataclass
class ToolResult:
    ok: bool
    executed: bool
    spoken: str
    reason: str
    data: dict[str, Any] = field(default_factory=dict)


class LocalToolExecutor:
    def __init__(
        self,
        settings: Settings,
        *,
        launch: Optional[LaunchFn] = None,
        force_local: bool = False,
    ) -> None:
        self._settings = settings
        self._launch = launch
        self._force_local = force_local

    @property
    def backend(self) -> str:
        return detect_backend(self._settings)

    def run(
        self,
        spec: ToolSpec,
        *,
        target: Target,
        arguments: dict[str, Any],
        session_id: str = "-",
    ) -> ToolResult:
        backend = self.backend
        if backend == "off":
            return ToolResult(
                ok=True,
                executed=False,
                spoken=_planned(spec, target, arguments),
                reason="tools_disabled",
            )
        if target == "mac" and not self._force_local:
            return ToolResult(
                ok=True,
                executed=False,
                spoken="I'll do that on the Mac once the client is connected.",
                reason="deferred_mac",
            )
        try:
            data, spoken = self._dispatch(spec, target, arguments)
        except ToolExecutionError as exc:
            logger.info(
                "tool failed name=%s reason=%s",
                spec.name,
                exc,
                extra={"session_id": session_id},
            )
            return ToolResult(ok=False, executed=False, spoken=str(exc), reason="tool_failed")
        logger.info(
            "tool executed name=%s target=%s backend=%s",
            spec.name,
            target,
            backend,
            extra={"session_id": session_id},
        )
        return ToolResult(ok=True, executed=True, spoken=spoken, reason="executed", data=data)

    def _dispatch(
        self, spec: ToolSpec, target: Target, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        if spec.name == "open_application":
            return self._open_application(arguments)
        if spec.name == "open_path":
            return self._open_path(target, arguments)
        if spec.name == "list_directory":
            return self._list_directory(target, arguments)
        if spec.name == "get_system_info":
            return self._system_info(target)
        if spec.name == "create_folder":
            return self._create_folder(target, arguments)
        if spec.name == "create_file":
            return self._create_file(target, arguments)
        if spec.name == "delete_path":
            return self._delete_path(target, arguments)
        if spec.name == "run_terminal":
            return self._run_terminal(arguments)
        raise ToolExecutionError(f"{spec.name} is not implemented on this brain.")

    def _open_application(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        application = str(arguments.get("application") or "")
        argv = app_argv(application, backend=self.backend)
        launch_app(argv, launch=self._launch)
        return {"application": application, "argv": argv}, f"Opening {application}."

    def _open_path(self, target: Target, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        path = resolve_user_path(
            str(arguments["path"]),
            self._settings,
            target=target,
            must_exist=True,
            destructive=False,
        )
        application = arguments.get("application")
        app_name = str(application).strip() if application else ""
        if app_name:
            argv = path_argv(str(path), application=app_name, backend=self.backend)
            launch_app(argv, launch=self._launch)
            spoken = f"Opening {path.name} in {app_name}."
        elif self.backend == "windows" and self._launch is None:
            os.startfile(str(path))  # type: ignore[attr-defined]
            argv = [str(path)]
            spoken = f"Opening {path.name}."
        else:
            argv = path_argv(str(path), application=None, backend=self.backend)
            launch_app(argv, launch=self._launch)
            spoken = f"Opening {path.name}."
        return {"path": str(path), "application": app_name or None, "argv": argv}, spoken

    def _list_directory(self, target: Target, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        folder = resolve_user_path(
            str(arguments["path"]),
            self._settings,
            target=target,
            must_exist=True,
            destructive=False,
        )
        if not folder.is_dir():
            raise ToolExecutionError("That path is not a folder.")
        names = sorted(p.name for p in folder.iterdir())[:_LIST_LIMIT]
        spoken = f"There are {len(names)} items in {folder.name}." if names else f"{folder.name} is empty."
        return {"path": str(folder), "entries": names}, spoken

    def _system_info(self, target: Target) -> tuple[dict[str, Any], str]:
        info = {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count() or 1,
            "requested_target": target,
            "backend": self.backend,
        }
        spoken = f"This computer is {info['system']} {info['release']} on {info['machine']}."
        return info, spoken

    def _create_folder(self, target: Target, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        folder = resolve_user_path(
            str(arguments["path"]), self._settings, target=target, must_exist=False, destructive=True
        )
        folder.mkdir(parents=True, exist_ok=True)
        return {"path": str(folder)}, f"Created folder {folder.name}."

    def _create_file(self, target: Target, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        path = resolve_user_path(
            str(arguments["path"]), self._settings, target=target, must_exist=False, destructive=True
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(arguments.get("content") or ""), encoding="utf-8")
        return {"path": str(path)}, f"Created {path.name}."

    def _delete_path(self, target: Target, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        path = resolve_user_path(
            str(arguments["path"]), self._settings, target=target, must_exist=True, destructive=True
        )
        if path.is_dir():
            _delete_tree(path)
        else:
            path.unlink()
        return {"path": str(path)}, f"Deleted {path.name}."

    def _run_terminal(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], str]:
        command = str(arguments.get("command") or "")
        if command_is_forbidden(command):
            raise ToolExecutionError("That command is blocked by safety policy.")
        argv = safe_argv(command)
        cwd = workspace_root(self._settings) or user_home()
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._settings.jarvis_terminal_timeout_seconds,
                env=_safe_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionError("That command timed out.") from exc
        except FileNotFoundError as exc:
            raise ToolExecutionError("I couldn't find that program.") from exc
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        clipped = output[:_OUTPUT_LIMIT]
        spoken = "Command finished." if completed.returncode == 0 else "Command finished with an error."
        return {
            "argv": argv,
            "cwd": str(cwd),
            "returncode": completed.returncode,
            "output": clipped,
        }, spoken


def detect_backend(settings: Settings) -> str:
    if not settings.jarvis_tools_enabled:
        return "off"
    choice = (settings.jarvis_tools_backend or "auto").strip().lower()
    if choice in {"off", "disabled"}:
        return "off"
    if choice == "auto":
        return "windows" if os.name == "nt" else "posix"
    if choice in {"windows", "posix"}:
        return choice
    return "off"


async def apply_execution(
    gated: GatedIntent,
    *,
    registry: ToolRegistry,
    executor: LocalToolExecutor,
    bridge: Any = None,
    memory: Any = None,
) -> GatedIntent:
    if gated.type != "tool_call" or gated.safety != "allowed" or not gated.tool or not gated.target:
        return gated
    spec = registry.require(gated.tool)
    if spec.name in BRAIN_LOCAL_TOOLS:
        if memory is None:
            result = ToolResult(
                ok=False,
                executed=False,
                spoken="Memory is not available.",
                reason="memory_unavailable",
            )
        else:
            ok, spoken, reason, data = memory.apply_remember(gated.arguments_or_empty)
            result = ToolResult(ok=ok, executed=ok, spoken=spoken, reason=reason, data=data)
    elif gated.target == "mac":
        if bridge is None:
            result = ToolResult(
                ok=True,
                executed=False,
                spoken="I'll do that on the Mac once the client is connected.",
                reason="deferred_mac",
            )
        else:
            result = await bridge.run_tool(
                spec,
                arguments=gated.arguments_or_empty,
                session_id=gated.session_id,
            )
    else:
        result = executor.run(
            spec,
            target=gated.target,
            arguments=gated.arguments_or_empty,
            session_id=gated.session_id,
        )
    updated = GatedIntent(
        type=gated.type,
        safety=gated.safety,
        message=result.spoken,
        spoken_reply=result.spoken,
        session_id=gated.session_id,
        executed=result.executed,
        confirmed=gated.confirmed,
        confirmation_id=gated.confirmation_id,
        tool=gated.tool,
        target=gated.target,
        arguments=gated.arguments,
        risk=gated.risk,
        requires_confirmation=gated.requires_confirmation,
        reason=result.reason,
        model=gated.model,
        prompt_tokens=gated.prompt_tokens,
        completion_tokens=gated.completion_tokens,
        total_tokens=gated.total_tokens,
        latency_ms=gated.latency_ms,
        parse_recovered=gated.parse_recovered,
        result=result.data or None,
    )
    if memory is not None:
        memory.record_task(
            session_id=updated.session_id,
            tool=updated.tool,
            target=updated.target,
            arguments=updated.arguments_or_empty,
            spoken=updated.spoken_reply,
            reason=updated.reason,
            executed=updated.executed,
        )
        if updated.executed and updated.tool == "open_application":
            app = str(updated.arguments_or_empty.get("application") or "")
            if app:
                memory.set_alias(app, "application", app)
    return updated


def _planned(spec: ToolSpec, target: str, arguments: dict[str, Any]) -> str:
    if spec.name == "open_application":
        return f"Opening {arguments.get('application', 'the application')}."
    return f"Planning {spec.name} on {target}."


def _delete_tree(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            _delete_tree(child)
        else:
            child.unlink()
    path.rmdir()


def _safe_env() -> dict[str, str]:
    keep = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.setdefault("PATH", os.defpath)
    return env
