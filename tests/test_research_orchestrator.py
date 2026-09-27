from datetime import datetime

from astraquant.lineage.manifests import RunManifest
from astraquant.research.orchestrator import ResearchOrchestrator
from astraquant.research.preregistration import ExperimentPreregistration
from astraquant.validation.promotion import ResearchStage
from astraquant.validation.results import ValidationCheck, ValidationLevel, ValidationReport


def _prereg() -> ExperimentPreregistration:
    return ExperimentPreregistration(
        experiment_id="EXP-R001",
        frozen_at=datetime(2026, 1, 1),
        hypothesis="test hypothesis",
        mechanism="test mechanism",
        universe_definition="frozen",
        sample_period="frozen",
        target_definition="forward return",
        baseline_definition="baseline",
        candidate_definition="candidate",
        feature_versions={"rs": "v1"},
        primary_metrics=("rank_ic",),
        walk_forward_protocol="rolling",
    )


def _run() -> RunManifest:
    return RunManifest(
        run_id="RUN-1",
        experiment_id="EXP-R001",
        created_at=datetime(2026, 1, 2),
        dataset_id="DS-1",
        code_version="abc",
        parameters={},
        feature_versions={"rs": "v1"},
        trial_number=1,
        selection_role="walk_forward_test",
    )


def test_orchestrator_preserves_governance_chain():
    report = ValidationReport(experiment_id="EXP-R001")
    report.add(
        ValidationCheck(
            level=ValidationLevel.ROLLING_WALK_FORWARD_OOS,
            name="wfo",
            status="PASS",
        )
    )
    outcome = ResearchOrchestrator().finalize_run(
        preregistration=_prereg(),
        run_manifest=_run(),
        validation_report=report,
        target_stage=ResearchStage.OOS_VALIDATED,
    )
    assert outcome.promotion_result.passed
    assert outcome.run_id == "RUN-1"
