from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from astraquant.research.feature_panel_integration import AvailabilityStatus


class BaselineSimulationMode(str, Enum):
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"
    FORMAL_RESEARCH = "FORMAL_RESEARCH"


def _parse_enum_value(value, enum_type, *, field_name: str):
    if isinstance(value, enum_type):
        return value
    if value is None:
        raise ValueError(f"{field_name} must not be null")
    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} must be {enum_type.__name__} or a recognized string"
        )
    normalized = value.strip().upper()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    try:
        return enum_type(normalized)
    except ValueError as exc:
        raise ValueError(
            f"unrecognized {field_name}: {value!r}"
        ) from exc


@dataclass(frozen=True)
class BaselineCATechnicalApproval:
    event_id: str
    approved: bool
    source: str

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("baseline CA approval requires event_id")
        if type(self.approved) is not bool:
            raise ValueError("baseline CA approval approved must be bool")
        if not self.source.strip():
            raise ValueError("baseline CA approval requires explicit source")


@dataclass(frozen=True)
class BaselineSimulationContext:
    """Opt-in gate for baseline_60d simulator integration.

    SYNTHETIC_FIXTURE is the only executable mode in this integration revision.

    The existing feature-panel integrator validates availability declarations,
    manifest identity, epoch, and per-artifact SHA256 while hydrating data, but
    it does not currently emit a simulator-verifiable eligibility token bound to
    the exact PreparedResearchRun. Until such a canonical handoff exists,
    FORMAL_RESEARCH remains unconditionally fail-closed here. A caller-provided
    VERIFIED enum/string or free-form source text is not sufficient evidence.

    CA technical transforms always require per-event evidence input; canonical
    accounting-event presence is never treated as technical approval.
    """

    mode: BaselineSimulationMode | str
    pit_data_gate_status: AvailabilityStatus | str = AvailabilityStatus.UNAVAILABLE
    pit_data_gate_source: str | None = None
    ca_approvals: tuple[BaselineCATechnicalApproval, ...] = ()

    def __post_init__(self) -> None:
        mode = _parse_enum_value(
            self.mode,
            BaselineSimulationMode,
            field_name="baseline simulation mode",
        )
        status = _parse_enum_value(
            self.pit_data_gate_status,
            AvailabilityStatus,
            field_name="baseline availability status",
        )
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "pit_data_gate_status", status)

        if self.pit_data_gate_source is not None:
            if not isinstance(self.pit_data_gate_source, str):
                raise ValueError("pit_data_gate_source must be a string or null")
            if not self.pit_data_gate_source.strip():
                raise ValueError("pit_data_gate_source must not be blank")

        seen: dict[str, BaselineCATechnicalApproval] = {}
        for item in self.ca_approvals:
            if not isinstance(item, BaselineCATechnicalApproval):
                raise ValueError(
                    "ca_approvals must contain BaselineCATechnicalApproval"
                )
            prior = seen.get(item.event_id)
            if prior is not None and prior != item:
                raise ValueError(
                    f"conflicting baseline CA approvals: {item.event_id}"
                )
            seen[item.event_id] = item

    def require_runnable(self) -> None:
        """Apply the single canonical baseline runtime gate.

        Formal execution is intentionally unavailable in this revision even if
        the caller supplies VERIFIED and arbitrary source text.
        """
        if self.mode is BaselineSimulationMode.FORMAL_RESEARCH:
            raise RuntimeError(
                "BASELINE_FORMAL_DATA_GATE_BLOCKED: no canonical eligibility "
                "evidence object is currently bound to PreparedResearchRun; "
                "FORMAL_RESEARCH is disabled"
            )
        if self.mode is not BaselineSimulationMode.SYNTHETIC_FIXTURE:
            # Defensive fail-closed guard even though __post_init__ normalizes.
            raise RuntimeError(
                f"BASELINE_SIMULATION_MODE_BLOCKED:{self.mode!r}"
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
