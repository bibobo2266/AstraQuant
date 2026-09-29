from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar


T = TypeVar("T")


class UnsupportedComponentError(ValueError):
    pass


@dataclass
class ComponentRegistry(Generic[T]):
    kind: str
    _handlers: dict[str, T] = field(default_factory=dict)

    def register(self, name: str, handler: T) -> None:
        key = str(name).strip().upper()
        if not key:
            raise ValueError("component name must be non-empty")
        if key in self._handlers:
            raise ValueError(f"{self.kind} component already registered: {key}")
        self._handlers[key] = handler

    def get(self, name: str) -> T:
        key = str(name).strip().upper()
        try:
            return self._handlers[key]
        except KeyError as exc:
            raise UnsupportedComponentError(
                f"unsupported {self.kind} component: {key}; "
                f"registered={sorted(self._handlers)}"
            ) from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
