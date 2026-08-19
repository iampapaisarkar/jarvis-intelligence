"""Execute Mac tools after local registry, schema, and safety checks."""

from __future__ import annotations

from typing import Any, Optional

from server.config import Settings
from server.safety.confirm import ConfirmationStore
from server.safety.engine import SafetyEngine
from server.tools.apps import LaunchFn
from server.tools.base import ToolValidationError, UnknownToolError
from server.tools.catalog import default_registry
from server.tools.executor import LocalToolExecutor, ToolResult
from server.tools.registry import ToolRegistry
from server.utils.logger import get_logger

logger = get_logger("jarvis.mac.client")


class MacToolRunner:
    """Runs on the Mac. Network payloads are treated as untrusted."""

    def __init__(
        self,
        settings: Settings,
        *,
        launch: Optional[LaunchFn] = None,
        registry: Optional[ToolRegistry] = None,
    ) -> None:
        self._registry = registry or default_registry()
        self._engine = SafetyEngine(self._registry, ConfirmationStore(ttl_seconds=60))
        self._executor = LocalToolExecutor(settings, launch=launch, force_local=True)

    def handle_request(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        session_id: str = "-",
    ) -> ToolResult:
        try:
            spec = self._registry.require(tool)
        except UnknownToolError:
            return ToolResult(
                ok=False,
                executed=False,
                spoken="I don't know that action.",
                reason="unknown_tool",
            )
        if "mac" not in spec.allowed_targets:
            return ToolResult(
                ok=False,
                executed=False,
                spoken="That action is not allowed on the Mac.",
                reason="wrong_target",
            )
        try:
            validated = spec.validate_args(arguments)
        except ToolValidationError:
            return ToolResult(
                ok=False,
                executed=False,
                spoken="Those arguments are not valid.",
                reason="invalid_arguments",
            )
        status, _reason, spoken = self._engine.review_tool(
            spec, target="mac", arguments=validated
        )
        if status == "denied":
            logger.info(
                "mac client denied tool=%s",
                spec.name,
                extra={"session_id": session_id},
            )
            return ToolResult(ok=False, executed=False, spoken=spoken, reason="blocked_by_policy")
        return self._executor.run(
            spec,
            target="mac",
            arguments=validated,
            session_id=session_id,
        )
