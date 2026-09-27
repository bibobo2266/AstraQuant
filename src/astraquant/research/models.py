from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    hypothesis: str
    baseline: str
    candidate: str
    frozen_at: datetime
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Trial:
    trial_id: str
    experiment_id: str
    created_at: datetime
    dataset_version: str
    code_version: str
    parameters: dict[str, Any]
    metrics: dict[str, float]
    selected_for_next_step: bool
    reason: str
