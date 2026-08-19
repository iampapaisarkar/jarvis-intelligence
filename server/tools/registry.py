from __future__ import annotations

from typing import Iterable, Iterator

from server.tools.base import ToolSpec, UnknownToolError


class ToolRegistry:
    """The only catalog of actions the LLM is allowed to name."""

    def __init__(self, tools: Iterable[ToolSpec]) -> None:
        self._tools = {spec.name: spec for spec in tools}

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def require(self, name: str) -> ToolSpec:
        spec = self.get(name)
        if spec is None:
            raise UnknownToolError(name)
        return spec

    def names(self) -> list[str]:
        return list(self._tools)

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[ToolSpec]:
        return iter(self._tools.values())

    def __contains__(self, name: str) -> bool:
        return name in self._tools
