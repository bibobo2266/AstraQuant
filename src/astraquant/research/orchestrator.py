from __future__ import annotations

from dataclasses import dataclass

from astraquant.lineage.manifests import RunManifest
from astraquant.research.preregistration import ExperimentPreregistration
from astraquant.validation.policy import PromotionPolicy
from astraquant.validation.promotion import GateResult, ResearchStage
from astraquant.validation.results import ValidationReport


@dataclass(frozen=True)
class ResearchRunOutcome:
    preregistration_id: str
    run_id: str
    experiment_id: str
    validation_report: ValidationReport
    promotion_result: GateResult


class ResearchOrchestrator:
    """Coordinates governance objects without running strategy logic."""

    def __init__(self, promotion_policy: PromotionPolicy | None = None) -> None:
        self.promotion_policy = promotion_policy or PromotionPolicy.default()

    def finalize_run(
        self,
        *,
        preregistration: ExperimentPreregistration,
        run_manifest: RunManifest,
        validation_report: ValidationReport,
        target_stage: ResearchStage,
    ) -> ResearchRunOutcome:
        preregistration.validate()

        if run_manifest.experiment_id != preregistration.experiment_id:
            raise ValueError("run manifest experiment_id does not match preregistration")
        if validation_report.experiment_id != preregistration.experiment_id:
            raise ValueError("validation report experiment_id does not match preregistration")

        promotion = self.promotion_policy.evaluate(target_stage, validation_report)

        return ResearchRunOutcome(
            preregistration_id=preregistration.experiment_id,
            run_id=run_manifest.run_id,
            experiment_id=preregistration.experiment_id,
            validation_report=validation_report,
            promotion_result=promotion,
        )
