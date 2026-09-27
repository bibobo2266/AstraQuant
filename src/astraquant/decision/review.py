from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class HumanDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    packet_id: str
    reviewer: str
    decision: HumanDecision
    reason: str
    reviewed_at: datetime


class ReviewHistory:
    """Append-only human review history."""

    def __init__(self) -> None:
        self._records: list[ReviewRecord] = []
        self._ids: set[str] = set()

    def append(self, record: ReviewRecord) -> None:
        if record.review_id in self._ids:
            raise ValueError(f"duplicate review id: {record.review_id}")
        if not record.reason.strip():
            raise ValueError("human review requires a reason")
        self._records.append(record)
        self._ids.add(record.review_id)

    def for_packet(self, packet_id: str) -> tuple[ReviewRecord, ...]:
        return tuple(x for x in self._records if x.packet_id == packet_id)

    def latest_for_packet(self, packet_id: str) -> ReviewRecord | None:
        records = self.for_packet(packet_id)
        return records[-1] if records else None
