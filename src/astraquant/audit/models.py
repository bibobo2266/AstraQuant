from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DecisionAuditTrail:
    experiment_id: str
    run_id: str
    dataset_id: str
    packet_id: str
    review_id: str
    intent_id: str
    created_at: datetime

    def validate(self) -> None:
        values = {
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "dataset_id": self.dataset_id,
            "packet_id": self.packet_id,
            "review_id": self.review_id,
            "intent_id": self.intent_id,
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(f"missing audit identifiers: {', '.join(missing)}")
