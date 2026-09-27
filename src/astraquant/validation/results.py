from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class ValidationLevel(IntEnum):
    MECHANISM_PLAUSIBLE = 1
    DESCRIPTIVE_ASSOCIATION = 2
    CLUSTER_BLOCK_INFERENCE = 3
    MULTIPLE_TEST_ADJUSTED = 4
    PLACEBO_FALSIFICATION = 5
    TEMPORAL_REPLAY = 6
    PARAMETER_PLATEAU = 7
    EXECUTION_SENSITIVITY = 8
    TEMPORAL_REPLICATION = 9
    ROLLING_WALK_FORWARD_OOS = 10
    LOCKED_FUTURE_OOS = 11


@dataclass(frozen=True)
class ValidationCheck:
    level: ValidationLevel
    name: str
    status: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        allowed = {"PASS", "FAIL", "LIMITED", "NOT_TESTED"}
        if self.status not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")


@dataclass
class ValidationReport:
    experiment_id: str
    checks: list[ValidationCheck] = field(default_factory=list)

    def add(self, check: ValidationCheck) -> None:
        if any(x.level == check.level and x.name == check.name for x in self.checks):
            raise ValueError(f"duplicate validation check: {check.level}/{check.name}")
        self.checks.append(check)

    def passed_levels(self) -> tuple[int, ...]:
        return tuple(sorted({int(x.level) for x in self.checks if x.status == "PASS"}))

    def strongest_passed_level(self) -> int | None:
        levels = self.passed_levels()
        return max(levels) if levels else None

    def has_explicit_pass(self, level: ValidationLevel) -> bool:
        return any(x.level == level and x.status == "PASS" for x in self.checks)
