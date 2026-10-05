"""AQ-EXP-DATA-001 r2 diagnostic contracts; no execution or gate authority.

The runner integration belongs to AQ-EXP-RUNNER-001. These pure functions
preserve source evidence and demonstrate chronological holding-data semantics.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date
from typing import Mapping


LIMITED = "ELIGIBLE_WITH_PIT_EVIDENCE_INCOMPLETE"
FEATURES = ("ma120", "n60", "atr14", "low20")


def map_source_row(row: Mapping[str, object]) -> dict[str, object]:
    """Lossless mapping, not permission to execute a SOURCE_EVIDENCE row."""
    required = {
        "date", "stock_id", "limited_exploration_label",
        "baseline_issue_a_any", "baseline_issue_b_any", "baseline_issue_c_any",
        "baseline_evidence_state", "raw_version_evidence_reason",
        "baseline_all_four_numeric_computable",
        "baseline_limited_exploration_eligible",
    }
    for feature in FEATURES:
        required.update(f"{feature}_{suffix}" for suffix in (
            "issue_a", "issue_b", "issue_c", "c_reason", "b_known",
            "b_event_count", "b_event_ids", "b_reasons", "evidence_state",
            "dominant_problem_class", "numeric_computable",
            "limited_exploration_eligible",
        ))
    missing = required - row.keys()
    if missing:
        raise ValueError(f"missing source evidence columns: {sorted(missing)}")
    if row["date"] is None or not str(row["stock_id"] or "").strip():
        raise ValueError("missing logical key")
    flags = [row[f"baseline_issue_{x}_any"] for x in "abc"]
    if any(type(value) is not bool for value in flags):
        raise ValueError("A/B/C must be explicit booleans, not missing or strings")
    a, b, c = flags
    for letter, aggregate in zip("abc", flags):
        feature_flags = [row[f"{feature}_issue_{letter}"] for feature in FEATURES]
        if any(type(value) is not bool for value in feature_flags):
            raise ValueError("feature A/B/C must be explicit booleans")
        if any(feature_flags) != aggregate:
            raise ValueError("aggregate A/B/C contradicts feature evidence")
    for feature in FEATURES:
        if row[f"{feature}_issue_c"] and not row[f"{feature}_c_reason"]:
            raise ValueError("C requires feature reason")
        if row[f"{feature}_issue_b"] and not row[f"{feature}_b_reasons"]:
            raise ValueError("B requires feature reasons")
    if not a or not row["raw_version_evidence_reason"]:
        raise ValueError("frozen v1 source requires A and its evidence reason")
    label = row["limited_exploration_label"]
    limited = not b and not c
    if label != (LIMITED if limited else "NOT_ELIGIBLE"):
        raise ValueError("label contradicts A/B/C")
    if row["baseline_all_four_numeric_computable"] is not (not c):
        raise ValueError("numeric flag contradicts C")
    if row["baseline_limited_exploration_eligible"] is not limited:
        raise ValueError("limited flag contradicts B/C")
    if limited and row["baseline_evidence_state"] != "INDETERMINATE":
        raise ValueError("A-only source cannot be VERIFIED or supported unaffected")
    result = deepcopy(dict(row))
    result["source_eligibility_label"] = label
    result["eligibility_status"] = "UNAVAILABLE" if c else "BLOCKED" if b else LIMITED
    result["reason_code"] = (
        "C_NOT_COMPUTABLE" if c else "B_ECONOMIC_CONTENT_UNRESOLVED" if b
        else "A_PIT_EVIDENCE_INCOMPLETE"
    )
    result["reason_detail"] = str(row["raw_version_evidence_reason"])
    return result


@dataclass(frozen=True)
class HoldingDataAudit:
    entry_session: date
    last_checked_session: date
    last_reliable_session: date
    status: str = "OPEN"
    first_problem_session: date | None = None
    reason: str | None = None
    economic_state: str = "PIT_EVIDENCE_INCOMPLETE"
    portfolio_continuation_blocked: bool = False


def advance_holding_data(
    previous: HoldingDataAudit,
    *,
    session: date,
    expected_next_session: date,
    in_all_liquid: bool,
    holding_evidence: str,
    reason: str,
    canonical_exit_observed: bool = False,
    period_end: bool = False,
) -> HoldingDataAudit:
    """Synthetic contract oracle: feed each trusted common session in order.

    RELIABLE means explicit holding-path evidence (including valuation/CA),
    not simply a signal eligibility row. No future rows are accepted here.
    """
    if session != expected_next_session or session <= previous.last_checked_session:
        raise ValueError("missing, duplicate or reordered common session")
    if type(in_all_liquid) is not bool:
        raise ValueError("membership must be explicit; never infer it from a missing row")
    if holding_evidence not in {"RELIABLE", "MISSING", "ECONOMIC_UNRESOLVED", "NOT_COMPUTABLE"}:
        raise ValueError("unknown holding evidence")
    if previous.status != "OPEN":
        return previous  # A later repaired row never uncensors or reopens this record.
    if holding_evidence != "RELIABLE":
        if not reason.strip():
            raise ValueError("problem requires a reason")
        return replace(
            previous, last_checked_session=session, status="DATA_CENSORED",
            first_problem_session=session, reason=reason,
            economic_state="UNRESOLVED" if holding_evidence == "ECONOMIC_UNRESOLVED"
            else previous.economic_state,
            portfolio_continuation_blocked=True,
        )
    return replace(
        previous, last_checked_session=session, last_reliable_session=session,
        status="CLOSED" if canonical_exit_observed else "OPEN_AT_END" if period_end else "OPEN",
    )
