from __future__ import annotations

from dataclasses import dataclass

from .assumptions import ExecutionAssumptions


@dataclass(frozen=True)
class VersionedExecutionAssumptions:
    assumptions_id: str
    version: str
    assumptions: ExecutionAssumptions


class ExecutionAssumptionRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], VersionedExecutionAssumptions] = {}

    def register(self, item: VersionedExecutionAssumptions) -> None:
        key = (item.assumptions_id, item.version)
        if key in self._items:
            raise ValueError(
                f"execution assumptions already registered: "
                f"{item.assumptions_id}@{item.version}"
            )
        self._items[key] = item

    def get(self, assumptions_id: str, version: str) -> VersionedExecutionAssumptions:
        return self._items[(assumptions_id, version)]
