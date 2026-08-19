"""Tool metadata. Phase 4 validates plans; it does not execute OS actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Type

from pydantic import BaseModel, ValidationError

Risk = Literal["low", "medium", "high"]
Target = Literal["windows", "mac"]


class ToolError(Exception):
    """Raised when a tool name or arguments cannot be used."""


class UnknownToolError(ToolError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Unknown tool: {name}")


class ToolValidationError(ToolError):
    pass


class ToolExecutionDisabled(ToolError):
    """Phase 4 never runs tools. Safety (5) and Windows tools (6) come later."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    allowed_targets: tuple[Target, ...]
    risk: Risk
    requires_confirmation: bool
    args_model: Type[BaseModel]

    def validate_args(self, raw: Any) -> dict[str, Any]:
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ToolValidationError(f"Tool {self.name} arguments must be a JSON object")
        try:
            return self.args_model.model_validate(raw).model_dump()
        except ValidationError as exc:
            raise ToolValidationError(f"Invalid arguments for {self.name}: {exc.errors()[0]['msg']}") from exc

    def resolve_target(self, requested: str | None, default: Target) -> Target:
        allowed = set(self.allowed_targets)
        if requested in allowed:
            return requested  # type: ignore[return-value]
        if default in allowed:
            return default
        return self.allowed_targets[0]

    def prompt_entry(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        return {
            "name": self.name,
            "description": self.description,
            "targets": list(self.allowed_targets),
            "risk": self.risk,
            "arguments": schema.get("properties") or {},
            "required": schema.get("required") or [],
        }

    def execute(self, arguments: dict[str, Any]) -> None:
        raise ToolExecutionDisabled(
            f"{self.name} is registered but execution is disabled until Phase 6 "
            "(after the Phase 5 safety engine)."
        )
