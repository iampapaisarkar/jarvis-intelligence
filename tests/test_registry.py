from server.tools.base import ToolExecutionDisabled, ToolValidationError, UnknownToolError
from server.tools.catalog import default_registry, resolve_application_alias


def test_default_registry_names_are_stable():
    registry = default_registry()
    assert registry.names() == [
        "open_application",
        "list_directory",
        "get_system_info",
        "create_folder",
        "create_file",
        "delete_path",
        "run_terminal",
        "remember_preference",
    ]
    assert len(registry) == 8


def test_unknown_tool_is_rejected():
    registry = default_registry()
    try:
        registry.require("format_disk")
        assert False, "expected UnknownToolError"
    except UnknownToolError as exc:
        assert exc.name == "format_disk"


def test_open_application_aliases_vscode():
    spec = default_registry().require("open_application")
    args = spec.validate_args({"application": "vscode"})
    assert args["application"] == "Visual Studio Code"
    assert resolve_application_alias("VS Code") == "Visual Studio Code"


def test_open_application_rejects_empty_name():
    spec = default_registry().require("open_application")
    try:
        spec.validate_args({"application": "  "})
        assert False, "expected ToolValidationError"
    except ToolValidationError:
        pass


def test_create_folder_is_medium_and_needs_confirmation():
    spec = default_registry().require("create_folder")
    assert spec.risk == "medium"
    assert spec.requires_confirmation is True
    args = spec.validate_args({"path": "~/Projects/demo"})
    assert args["path"] == "~/Projects/demo"


def test_path_rejects_nul():
    spec = default_registry().require("list_directory")
    try:
        spec.validate_args({"path": "foo\x00bar"})
        assert False, "expected ToolValidationError"
    except ToolValidationError:
        pass


def test_target_falls_back_to_default():
    spec = default_registry().require("open_application")
    assert spec.resolve_target("linux", "windows") == "windows"
    assert spec.resolve_target("mac", "windows") == "mac"


def test_execute_is_disabled():
    spec = default_registry().require("open_application")
    try:
        spec.execute({"application": "Visual Studio Code"})
        assert False, "expected ToolExecutionDisabled"
    except ToolExecutionDisabled as exc:
        assert "Phase 6" in str(exc)
