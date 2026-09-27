from astraquant.validation.policy import PromotionPolicy
from astraquant.validation.promotion import ResearchStage
from astraquant.validation.results import ValidationCheck, ValidationLevel, ValidationReport


def test_robustness_promotion_requires_explicit_levels():
    report = ValidationReport(experiment_id="EXP-X")
    for level in (
        ValidationLevel.MULTIPLE_TEST_ADJUSTED,
        ValidationLevel.PLACEBO_FALSIFICATION,
        ValidationLevel.PARAMETER_PLATEAU,
        ValidationLevel.EXECUTION_SENSITIVITY,
    ):
        report.add(ValidationCheck(level=level, name=level.name, status="PASS"))

    result = PromotionPolicy.default().evaluate(ResearchStage.ROBUSTNESS_VALIDATED, report)
    assert not result.passed
    assert "ROLLING_WALK_FORWARD_OOS" in result.blockers


def test_robustness_promotion_passes_when_all_required_levels_pass():
    report = ValidationReport(experiment_id="EXP-X")
    for level in (
        ValidationLevel.MULTIPLE_TEST_ADJUSTED,
        ValidationLevel.PLACEBO_FALSIFICATION,
        ValidationLevel.PARAMETER_PLATEAU,
        ValidationLevel.EXECUTION_SENSITIVITY,
        ValidationLevel.ROLLING_WALK_FORWARD_OOS,
    ):
        report.add(ValidationCheck(level=level, name=level.name, status="PASS"))

    result = PromotionPolicy.default().evaluate(ResearchStage.ROBUSTNESS_VALIDATED, report)
    assert result.passed
