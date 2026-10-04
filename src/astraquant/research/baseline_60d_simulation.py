from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from astraquant.research.feature_panel_integration import AvailabilityStatus


class BaselineSimulationMode(str, Enum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    FORMAL_RESEARCH = "FORMAL_RESEARCH"


@dataclass(frozen=True)
class BaselineCATechnicalApproval:
    event_id: str
    approved: bool
    source: str

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("baseline CA approval requires event_id")
        if not self.source.strip():
            raise ValueError("baseline CA approval requires explicit source")


@dataclass(frozen=True)
class BaselineSimulationContext:
    """Opt-in gate for baseline_60d simulator integration.

    Synthetic fixtures may opt in explicitly for software acceptance. Formal
    research remains fail-closed until its upstream PIT/data gate is separately
    verified. CA technical transforms always require per-event evidence input;
    accounting-layer event presence is never treated as technical approval.
    """

    mode: BaselineSimulationMode
    pit_data_gate_status: AvailabilityStatus = AvailabilityStatus.UNAVAILABLE
    pit_data_gate_source: str | None = None
    ca_approvals: tuple[BaselineCATechnicalApproval, ...] = ()

    def __post_init__(self) -> None:
        seen: dict[str, BaselineCATechnicalApproval] = {}
        for item in self.ca_approvals:
            prior = seen.get(item.event_id)
            if prior is not None and prior != item:
                raise ValueError(
                    f"conflicting baseline CA approvals: {item.event_id}"
                )
            seen[item.event_id] = item

        if self.mode is BaselineSimulationMode.FORMAL_RESEARCH:
            if not self.pit_data_gate_source or not self.pit_data_gate_source.strip():
                raise ValueError(
                    "formal baseline data-gate status requires explicit source"
                )

    def require_runnable(self) -> None:
        if (
            self.mode is BaselineSimulationMode.FORMAL_RESEARCH
            and self.pit_data_gate_status is not AvailabilityStatus.VERIFIED
        ):
            raise RuntimeError(
                "BASELINE_FORMAL_DATA_GATE_BLOCKED: required feature inputs "
                f"have availability={self.pit_data_gate_status.value}"
            )

    def ca_approval(self, event_id: str) -> BaselineCATechnicalApproval:
        matches = [item for item in self.ca_approvals if item.event_id == event_id]
        if matches:
            return matches[0]
        return BaselineCATechnicalApproval(
            event_id=event_id,
            approved=False,
            source="UNPROVIDED_TECHNICAL_CA_EVIDENCE",
        )
