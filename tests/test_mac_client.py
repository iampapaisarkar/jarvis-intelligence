from mac_client.runner import MacToolRunner
from server.config import get_settings


def test_mac_runner_system_info(app_launcher):
    runner = MacToolRunner(get_settings(), launch=app_launcher)
    result = runner.handle_request("get_system_info", {}, session_id="s")
    assert result.executed is True
    assert result.reason == "executed"
    assert "system" in result.data


def test_mac_runner_unknown_tool(app_launcher):
    runner = MacToolRunner(get_settings(), launch=app_launcher)
    result = runner.handle_request("format_disk", {}, session_id="s")
    assert result.executed is False
    assert result.reason == "unknown_tool"


def test_mac_runner_blocks_system_path(app_launcher):
    runner = MacToolRunner(get_settings(), launch=app_launcher)
    result = runner.handle_request("delete_path", {"path": "/etc/passwd"}, session_id="s")
    assert result.executed is False
    assert result.reason == "blocked_by_policy"


def test_mac_runner_rejects_invalid_arguments(app_launcher):
    runner = MacToolRunner(get_settings(), launch=app_launcher)
    result = runner.handle_request("open_application", {}, session_id="s")
    assert result.executed is False
    assert result.reason == "invalid_arguments"
