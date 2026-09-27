from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ExperimentPreregistration:
    experiment_id: str
    frozen_at: datetime
    hypothesis: str
    mechanism: str
    universe_definition: str
    sample_period: str
    target_definition: str
    baseline_definition: str
    candidate_definition: str
    feature_versions: dict[str, str]
    primary_metrics: tuple[str, ...]
    secondary_metrics: tuple[str, ...] = field(default_factory=tuple)
    walk_forward_protocol: str | None = None
    execution_assumptions_id: str | None = None
    multiple_testing_plan: str | None = None
    falsification_plan: str | None = None
    promotion_criteria: tuple[str, ...] = field(default_factory=tuple)
    stop_conditions: tuple[str, ...] = field(default_factory=tuple)
    locked_oos_definition: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id is required")
        if not self.hypothesis.strip():
            raise ValueError("hypothesis is required")
        if not self.primary_metrics:
            raise ValueError("at least one primary metric is required")
        if self.locked_oos_definition and not self.walk_forward_protocol:
            raise ValueError("locked OOS requires an explicit walk-forward/validation protocol")
