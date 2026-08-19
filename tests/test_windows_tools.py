from pathlib import Path

from server.config import get_settings
from server.tools.catalog import default_registry
from server.tools.executor import LocalToolExecutor
from server.tools.paths import ToolExecutionError, resolve_user_path
from server.tools.terminal import safe_argv


def test_safe_argv_allows_python_version():
    assert safe_argv("python3 --version")[0] in {"python3", "python"}


def test_safe_argv_rejects_python_dash_c():
    try:
        safe_argv("python3 -c 'print(1)'")
        assert False, "expected ToolExecutionError"
    except ToolExecutionError:
        pass


def test_safe_argv_rejects_rm():
    try:
        safe_argv("rm -rf /tmp/x")
        assert False, "expected ToolExecutionError"
    except ToolExecutionError:
        pass


def test_create_list_delete_inside_home():
    settings = get_settings()
    executor = LocalToolExecutor(settings, launch=lambda _argv: None)
    registry = default_registry()
    folder = Path.home() / "Projects" / "phase6"
    result = executor.run(
        registry.require("create_folder"),
        target="windows",
        arguments={"path": "~/Projects/phase6"},
    )
    assert result.executed is True
    assert folder.is_dir()

    listed = executor.run(
        registry.require("list_directory"),
        target="windows",
        arguments={"path": "~/Projects"},
    )
    assert "phase6" in listed.data["entries"]

    deleted = executor.run(
        registry.require("delete_path"),
        target="windows",
        arguments={"path": "~/Projects/phase6"},
    )
    assert deleted.executed is True
    assert not folder.exists()


def test_mac_target_is_deferred():
    executor = LocalToolExecutor(get_settings(), launch=lambda _argv: None)
    result = executor.run(
        default_registry().require("open_application"),
        target="mac",
        arguments={"application": "Visual Studio Code"},
    )
    assert result.executed is False
    assert result.reason == "deferred_mac"


def test_open_application_uses_launcher(app_launcher):
    executor = LocalToolExecutor(get_settings(), launch=app_launcher)
    result = executor.run(
        default_registry().require("open_application"),
        target="windows",
        arguments={"application": "Visual Studio Code"},
    )
    assert result.executed is True
    assert app_launcher.calls
    assert app_launcher.calls[0][0] == "open"
    assert "Visual Studio Code" in app_launcher.calls[0]


def test_system_info_runs():
    result = LocalToolExecutor(get_settings(), launch=lambda _argv: None).run(
        default_registry().require("get_system_info"),
        target="windows",
        arguments={},
    )
    assert result.executed is True
    assert "system" in result.data


def test_terminal_python_version():
    result = LocalToolExecutor(get_settings(), launch=lambda _argv: None).run(
        default_registry().require("run_terminal"),
        target="windows",
        arguments={"command": "python3 --version"},
    )
    assert result.executed is True
    assert "Python" in (result.data.get("output") or "")


def test_path_outside_home_rejected():
    try:
        resolve_user_path("/etc/passwd", get_settings(), target="mac", must_exist=False)
        assert False, "expected ToolExecutionError"
    except ToolExecutionError:
        pass
