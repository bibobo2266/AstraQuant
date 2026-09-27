from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResearchStage(str, Enum):
    IDEA = "IDEA"
    EXPERIMENTAL = "EXPERIMENTAL"
    BACKTESTED = "BACKTESTED"
    OOS_VALIDATED = "OOS_VALIDATED"
    ROBUSTNESS_VALIDATED = "ROBUSTNESS_VALIDATED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    PRODUCTION = "PRODUCTION"
    MONITORING = "MONITORING"
    RETIRED = "RETIRED"


@dataclass(frozen=True)
class GateResult:
    stage: ResearchStage
    passed: bool
    evidence: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def require_all(stage: ResearchStage, checks: dict[str, bool]) -> GateResult:
    evidence = [name for name, ok in checks.items() if ok]
    blockers = [name for name, ok in checks.items() if not ok]
    return GateResult(stage=stage, passed=not blockers, evidence=evidence, blockers=blockers)
