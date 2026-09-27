from __future__ import annotations

from dataclasses import dataclass

from .promotion import GateResult, ResearchStage, require_all
from .results import ValidationLevel, ValidationReport


@dataclass(frozen=True)
class PromotionPolicy:
    required_levels: dict[ResearchStage, tuple[ValidationLevel, ...]]

    @classmethod
    def default(cls) -> "PromotionPolicy":
        return cls(
            required_levels={
                ResearchStage.BACKTESTED: (
                    ValidationLevel.DESCRIPTIVE_ASSOCIATION,
                ),
                ResearchStage.OOS_VALIDATED: (
                    ValidationLevel.ROLLING_WALK_FORWARD_OOS,
                ),
                ResearchStage.ROBUSTNESS_VALIDATED: (
                    ValidationLevel.MULTIPLE_TEST_ADJUSTED,
                    ValidationLevel.PLACEBO_FALSIFICATION,
                    ValidationLevel.PARAMETER_PLATEAU,
                    ValidationLevel.EXECUTION_SENSITIVITY,
                    ValidationLevel.ROLLING_WALK_FORWARD_OOS,
                ),
            }
        )

    def evaluate(
        self,
        target_stage: ResearchStage,
        report: ValidationReport,
    ) -> GateResult:
        required = self.required_levels.get(target_stage, ())
        checks = {level.name: report.has_explicit_pass(level) for level in required}
        return require_all(target_stage, checks)
