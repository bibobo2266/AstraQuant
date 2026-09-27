from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResearchResultSummary:
    experiment_id: str
    run_id: str
    dataset_id: str
    headline_metrics: dict[str, float]
    evidence_supporting: tuple[str, ...] = field(default_factory=tuple)
    evidence_contradicting: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    unresolved_questions: tuple[str, ...] = field(default_factory=tuple)
    regime_notes: tuple[str, ...] = field(default_factory=tuple)
    turnover_notes: tuple[str, ...] = field(default_factory=tuple)
    execution_notes: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.experiment_id or not self.run_id or not self.dataset_id:
            raise ValueError("experiment_id, run_id, and dataset_id are required")
        if not self.headline_metrics:
            raise ValueError("headline_metrics cannot be empty")
