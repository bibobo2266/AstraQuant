from datetime import datetime

import pytest

from astraquant.research.preregistration import ExperimentPreregistration


def test_preregistration_requires_primary_metric():
    spec = ExperimentPreregistration(
        experiment_id="EXP-R001",
        frozen_at=datetime(2026, 1, 1),
        hypothesis="RS persistence adds value",
        mechanism="persistent leadership",
        universe_definition="frozen later",
        sample_period="frozen later",
        target_definition="forward return",
        baseline_definition="RS",
        candidate_definition="RS plus persistence",
        feature_versions={},
        primary_metrics=(),
    )
    with pytest.raises(ValueError):
        spec.validate()


def test_locked_oos_requires_validation_protocol():
    spec = ExperimentPreregistration(
        experiment_id="EXP-R001",
        frozen_at=datetime(2026, 1, 1),
        hypothesis="RS persistence adds value",
        mechanism="persistent leadership",
        universe_definition="frozen later",
        sample_period="frozen later",
        target_definition="forward return",
        baseline_definition="RS",
        candidate_definition="RS plus persistence",
        feature_versions={},
        primary_metrics=("rank_ic",),
        locked_oos_definition="future holdout",
    )
    with pytest.raises(ValueError):
        spec.validate()
