from datetime import datetime

import pytest

from astraquant.research.models import ExperimentSpec, Trial
from astraquant.research.registry import ExperimentRegistry
from astraquant.validation.promotion import ResearchStage, require_all


def test_frozen_experiment_id_cannot_be_overwritten():
    registry = ExperimentRegistry()
    spec = ExperimentSpec(
        experiment_id="EXP-R001",
        hypothesis="test",
        baseline="A",
        candidate="B",
        frozen_at=datetime(2026, 1, 1),
    )
    registry.register_experiment(spec)
    with pytest.raises(ValueError):
        registry.register_experiment(spec)


def test_trial_requires_registered_experiment():
    registry = ExperimentRegistry()
    trial = Trial(
        trial_id="T1",
        experiment_id="UNKNOWN",
        created_at=datetime(2026, 1, 1),
        dataset_version="d1",
        code_version="c1",
        parameters={},
        metrics={},
        selected_for_next_step=False,
        reason="test",
    )
    with pytest.raises(ValueError):
        registry.record_trial(trial)


def test_promotion_gate_exposes_blockers():
    result = require_all(
        ResearchStage.OOS_VALIDATED,
        {"walk_forward": True, "locked_oos": False},
    )
    assert not result.passed
    assert result.blockers == ["locked_oos"]
