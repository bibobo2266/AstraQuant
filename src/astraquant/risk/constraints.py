from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class RiskContext:
    symbol: str
    side: str
    quantity: float
    portfolio_state: dict[str, Any] = field(default_factory=dict)
    market_state: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RiskCheckResult:
    name: str
    passed: bool
    reason: str


class RiskConstraint(Protocol):
    name: str

    def evaluate(self, context: RiskContext) -> RiskCheckResult: ...


@dataclass(frozen=True)
class MaxPositionCountConstraint:
    max_positions: int
    name: str = "max_position_count"

    def evaluate(self, context: RiskContext) -> RiskCheckResult:
        current = int(context.portfolio_state.get("position_count", 0))
        opening_new = bool(context.portfolio_state.get("opening_new_position", False))
        passed = not (opening_new and current >= self.max_positions)
        reason = (
            f"position_count={current}, max_positions={self.max_positions}, "
            f"opening_new_position={opening_new}"
        )
        return RiskCheckResult(self.name, passed, reason)


def evaluate_constraints(
    constraints: list[RiskConstraint],
    context: RiskContext,
) -> tuple[RiskCheckResult, ...]:
    return tuple(constraint.evaluate(context) for constraint in constraints)
