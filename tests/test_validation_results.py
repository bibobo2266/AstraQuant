from astraquant.validation.results import (
    ValidationCheck,
    ValidationLevel,
    ValidationReport,
)


def test_higher_level_does_not_imply_lower_levels():
    report = ValidationReport(experiment_id="EXP-X")
    report.add(
        ValidationCheck(
            level=ValidationLevel.ROLLING_WALK_FORWARD_OOS,
            name="wfo",
            status="PASS",
        )
    )

    assert report.strongest_passed_level() == 10
    assert report.passed_levels() == (10,)
    assert not report.has_explicit_pass(ValidationLevel.MULTIPLE_TEST_ADJUSTED)


def test_validation_status_is_controlled():
    try:
        ValidationCheck(
            level=ValidationLevel.DESCRIPTIVE_ASSOCIATION,
            name="bad",
            status="MAYBE",
        )
    except ValueError:
        return
    raise AssertionError("invalid status should fail")
