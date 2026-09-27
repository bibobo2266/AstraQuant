import pytest

from astraquant.research.results import ResearchResultSummary


def test_result_summary_requires_headline_metrics():
    result = ResearchResultSummary(
        experiment_id="EXP-R001",
        run_id="RUN-1",
        dataset_id="DS-1",
        headline_metrics={},
    )
    with pytest.raises(ValueError):
        result.validate()


def test_result_summary_can_preserve_contradicting_evidence():
    result = ResearchResultSummary(
        experiment_id="EXP-R001",
        run_id="RUN-1",
        dataset_id="DS-1",
        headline_metrics={"rank_ic": 0.03},
        evidence_supporting=("positive IC",),
        evidence_contradicting=("weak 2022 regime",),
    )
    result.validate()
    assert result.evidence_contradicting == ("weak 2022 regime",)
