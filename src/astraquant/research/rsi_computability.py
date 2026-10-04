from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from astraquant.research.feature_cache import FeatureCache, FeatureCacheKey
from astraquant.research.strategy_config import ComponentSpec
from astraquant.research.technical_components import _rsi_value


STRICT_RSI_CONTRACT_VERSION = "RSI_COMPUTABILITY_V1_STRICT"
LEGACY_RSI_FORMULA_VERSION = "LEGACY_RSI_V1_UNCHANGED"


class TriState(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class RsiComputabilityReason(str, Enum):
    OK = "OK"
    CURRENT_INPUT_MISSING = "CURRENT_INPUT_MISSING"
    WARMUP_INSUFFICIENT = "WARMUP_INSUFFICIENT"
    HISTORY_GAP_POLICY_UNRESOLVED = "HISTORY_GAP_POLICY_UNRESOLVED"
    SESSION_GAP_NOT_AUDITABLE = "SESSION_GAP_NOT_AUDITABLE"
    RSI_DERIVED_COMPONENT_CONTRACT_NOT_MAPPED = (
        "RSI_DERIVED_COMPONENT_CONTRACT_NOT_MAPPED"
    )


@dataclass(frozen=True)
class SignalComputabilityContext:
    """Opt-in research computability contract for the legacy RSI family.

    expected_sessions must come from a trusted upstream session contract.
    This class never derives a supposedly-complete calendar from the stock panel.
    If no trusted sequence is supplied, strict RSI availability remains UNKNOWN
    once warmup is otherwise complete.
    """

    contract_version: str = STRICT_RSI_CONTRACT_VERSION
    expected_sessions: tuple[object, ...] | None = None
    expected_sessions_source: str | None = None

    def __post_init__(self) -> None:
        if self.contract_version != STRICT_RSI_CONTRACT_VERSION:
            raise ValueError(
                "unsupported signal computability contract: "
                f"{self.contract_version}"
            )
        if self.expected_sessions is None:
            return
        if not self.expected_sessions:
            raise ValueError("expected_sessions must be non-empty when supplied")
        if not self.expected_sessions_source or not self.expected_sessions_source.strip():
            raise ValueError(
                "expected_sessions_source is required when expected_sessions are supplied"
            )
        normalized = tuple(
            pd.Timestamp(value).normalize() for value in self.expected_sessions
        )
        if any(pd.isna(value) for value in normalized):
            raise ValueError("expected_sessions contains invalid dates")
        if len(set(normalized)) != len(normalized):
            raise ValueError("expected_sessions contains duplicates")
        if tuple(sorted(normalized)) != normalized:
            raise ValueError("expected_sessions must be strictly increasing")
        object.__setattr__(self, "expected_sessions", normalized)

    def validate_panel_coverage(self, panel: pd.DataFrame) -> None:
        if self.expected_sessions is None or panel.empty:
            return
        dates = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
        if dates.isna().any():
            raise ValueError("strict computability panel contains invalid dates")
        expected = tuple(self.expected_sessions)
        expected_set = set(expected)
        observed = tuple(pd.Timestamp(value).normalize() for value in dates.unique())
        outside = sorted(set(observed) - expected_set)
        if outside:
            raise ValueError(
                "panel contains dates outside expected_sessions contract: "
                + ", ".join(str(x.date()) for x in outside[:5])
            )
        if min(observed) < expected[0] or max(observed) > expected[-1]:
            raise ValueError("expected_sessions does not cover panel date range")


def combine_tristate(states: Iterable[TriState], op: str) -> TriState:
    values = tuple(states)
    op = str(op).upper()
    if not values:
        return TriState.TRUE
    if op == "AND":
        if TriState.FALSE in values:
            return TriState.FALSE
        if all(value is TriState.TRUE for value in values):
            return TriState.TRUE
        return TriState.UNKNOWN
    if op == "OR":
        if TriState.TRUE in values:
            return TriState.TRUE
        if all(value is TriState.FALSE for value in values):
            return TriState.FALSE
        return TriState.UNKNOWN
    raise ValueError(f"unsupported tri-state op: {op}")


def _validate_strict_panel(panel: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "stock_id", "close"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(
            f"RSI computability panel missing columns: {sorted(missing)}"
        )
    work = panel[["date", "stock_id", "close"]].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.normalize()
    work["stock_id"] = work["stock_id"].astype(str)
    work["close"] = pd.to_numeric(work["close"], errors="coerce")
    if work[["date", "stock_id"]].isna().any(axis=1).any():
        raise ValueError("strict computability requires explicit date and stock_id")
    if work.duplicated(["date", "stock_id"]).any():
        raise ValueError("strict computability panel has duplicate logical keys")
    expected_order = work.sort_values(["stock_id", "date"], kind="stable").index
    if not expected_order.equals(work.index):
        raise ValueError(
            "strict evaluate_prepared panel must be sorted by stock_id/date"
        )
    return work


def rsi_values(
    *,
    panel: pd.DataFrame,
    lookback: int,
    cache: FeatureCache,
    signal_context,
) -> pd.Series:
    key = FeatureCacheKey.build(
        source_revision=signal_context.source_revision,
        feature_name="rsi",
        params={"lookback": lookback},
        availability_policy=signal_context.availability_policy,
    )
    return cache.get_or_compute_view(
        key,
        lambda: _rsi_value(panel=panel, lookback=lookback),
    )


def rsi_value_availability(
    panel: pd.DataFrame,
    *,
    lookback: int,
    context: SignalComputabilityContext,
    diagnostic_rsi: pd.Series,
) -> pd.DataFrame:
    """Return strict availability while preserving legacy RSI numeric state.

    An explicit non-finite close or a missing expected session creates a history
    gap for that stock. Subsequent legacy RSI values remain diagnostic-only until
    a separately versioned recovery policy is approved. No reset/re-warm occurs.
    """
    if lookback <= 1:
        raise ValueError("RSI lookback must be > 1")
    work = _validate_strict_panel(panel)
    context.validate_panel_coverage(work)
    diagnostic = diagnostic_rsi.reindex(work.index)

    expected_pos: dict[pd.Timestamp, int] | None = None
    if context.expected_sessions is not None:
        expected_pos = {
            pd.Timestamp(day).normalize(): i
            for i, day in enumerate(context.expected_sessions)
        }

    computable = pd.Series(False, index=work.index, dtype=bool)
    reason = pd.Series("", index=work.index, dtype="object")
    missing_expected_before = pd.Series(False, index=work.index, dtype=bool)

    for _, group in work.groupby("stock_id", sort=False):
        history_gap_seen = False
        finite_delta_count = 0
        previous_close: float | None = None
        previous_date: pd.Timestamp | None = None

        for idx, row in group.iterrows():
            current_date = pd.Timestamp(row["date"]).normalize()
            current_close = (
                float(row["close"]) if pd.notna(row["close"]) else np.nan
            )
            current_finite = bool(np.isfinite(current_close))

            missing_expected = False
            if expected_pos is not None and previous_date is not None:
                missing_expected = (
                    expected_pos[current_date] - expected_pos[previous_date] > 1
                )
                if missing_expected:
                    history_gap_seen = True
            missing_expected_before.loc[idx] = missing_expected

            if not current_finite:
                reason.loc[idx] = (
                    RsiComputabilityReason.CURRENT_INPUT_MISSING.value
                )
                history_gap_seen = True
            elif history_gap_seen:
                reason.loc[idx] = (
                    RsiComputabilityReason.HISTORY_GAP_POLICY_UNRESOLVED.value
                )
            else:
                if previous_close is not None and np.isfinite(previous_close):
                    finite_delta_count += 1
                if finite_delta_count < lookback:
                    reason.loc[idx] = (
                        RsiComputabilityReason.WARMUP_INSUFFICIENT.value
                    )
                elif expected_pos is None:
                    reason.loc[idx] = (
                        RsiComputabilityReason.SESSION_GAP_NOT_AUDITABLE.value
                    )
                else:
                    computable.loc[idx] = True
                    reason.loc[idx] = RsiComputabilityReason.OK.value

            previous_close = current_close
            previous_date = current_date

    return pd.DataFrame(
        {
            "computable": computable,
            "reason": reason,
            "diagnostic_value": diagnostic,
            "missing_expected_row_before_current": missing_expected_before,
        },
        index=work.index,
    )


def _state_series(values: Sequence[TriState], index: pd.Index) -> pd.Series:
    return pd.Series(
        [value.value for value in values],
        index=index,
        dtype="object",
    )


def _reason_series(values: Sequence[str], index: pd.Index) -> pd.Series:
    return pd.Series(list(values), index=index, dtype="object")


def strict_condition_for_component(
    *,
    panel: pd.DataFrame,
    spec: ComponentSpec,
    legacy_bool: pd.Series,
    cache: FeatureCache,
    signal_context,
    computability_context: SignalComputabilityContext,
) -> tuple[pd.Series, pd.Series]:
    component_type = str(spec.type).upper()
    index = panel.index

    if component_type == "RSI":
        lookback = int(spec.params.get("lookback", 14))
        values = rsi_values(
            panel=panel,
            lookback=lookback,
            cache=cache,
            signal_context=signal_context,
        )
        availability = rsi_value_availability(
            panel,
            lookback=lookback,
            context=computability_context,
            diagnostic_rsi=values,
        )
        states: list[TriState] = []
        reasons: list[str] = []
        for idx in index:
            if not bool(availability.loc[idx, "computable"]):
                states.append(TriState.UNKNOWN)
                reasons.append(str(availability.loc[idx, "reason"]))
                continue
            ok = True
            if "min" in spec.params:
                ok = ok and float(values.loc[idx]) >= float(spec.params["min"])
            if "max" in spec.params:
                ok = ok and float(values.loc[idx]) <= float(spec.params["max"])
            states.append(TriState.TRUE if ok else TriState.FALSE)
            reasons.append(RsiComputabilityReason.OK.value)
        return _state_series(states, index), _reason_series(reasons, index)

    if component_type == "RSI_CROSS":
        lookback = int(spec.params.get("lookback", 14))
        level = float(spec.params.get("level", 50))
        values = rsi_values(
            panel=panel,
            lookback=lookback,
            cache=cache,
            signal_context=signal_context,
        )
        availability = rsi_value_availability(
            panel,
            lookback=lookback,
            context=computability_context,
            diagnostic_rsi=values,
        )
        stock_ids = panel["stock_id"].astype(str)
        previous_values = values.groupby(stock_ids, sort=False).shift(1)
        previous_computable = availability["computable"].groupby(
            stock_ids, sort=False
        ).shift(1)
        previous_reason = availability["reason"].groupby(
            stock_ids, sort=False
        ).shift(1)
        states: list[TriState] = []
        reasons: list[str] = []
        for idx in index:
            if not bool(availability.loc[idx, "computable"]):
                states.append(TriState.UNKNOWN)
                reasons.append(str(availability.loc[idx, "reason"]))
                continue
            if pd.isna(previous_computable.loc[idx]) or not bool(
                previous_computable.loc[idx]
            ):
                prior_reason = (
                    RsiComputabilityReason.WARMUP_INSUFFICIENT.value
                    if pd.isna(previous_reason.loc[idx])
                    else str(previous_reason.loc[idx])
                )
                states.append(TriState.UNKNOWN)
                reasons.append(f"PREVIOUS_RSI_{prior_reason}")
                continue
            crossed = bool(
                float(values.loc[idx]) > level
                and float(previous_values.loc[idx]) <= level
            )
            states.append(TriState.TRUE if crossed else TriState.FALSE)
            reasons.append(RsiComputabilityReason.OK.value)
        return _state_series(states, index), _reason_series(reasons, index)

    if component_type == "RSI_RELATIVE":
        fast = int(spec.params.get("fast_lookback", 13))
        slow = int(spec.params.get("slow_lookback", 26))
        fast_values = rsi_values(
            panel=panel,
            lookback=fast,
            cache=cache,
            signal_context=signal_context,
        )
        slow_values = rsi_values(
            panel=panel,
            lookback=slow,
            cache=cache,
            signal_context=signal_context,
        )
        fast_availability = rsi_value_availability(
            panel,
            lookback=fast,
            context=computability_context,
            diagnostic_rsi=fast_values,
        )
        slow_availability = rsi_value_availability(
            panel,
            lookback=slow,
            context=computability_context,
            diagnostic_rsi=slow_values,
        )
        states: list[TriState] = []
        reasons: list[str] = []
        for idx in index:
            if not bool(fast_availability.loc[idx, "computable"]):
                states.append(TriState.UNKNOWN)
                reasons.append(
                    f"FAST_{fast_availability.loc[idx, 'reason']}"
                )
            elif not bool(slow_availability.loc[idx, "computable"]):
                states.append(TriState.UNKNOWN)
                reasons.append(
                    f"SLOW_{slow_availability.loc[idx, 'reason']}"
                )
            else:
                states.append(
                    TriState.TRUE
                    if float(fast_values.loc[idx]) > float(slow_values.loc[idx])
                    else TriState.FALSE
                )
                reasons.append(RsiComputabilityReason.OK.value)
        return _state_series(states, index), _reason_series(reasons, index)

    if "RSI" in component_type:
        return (
            pd.Series(
                TriState.UNKNOWN.value,
                index=index,
                dtype="object",
            ),
            pd.Series(
                RsiComputabilityReason.RSI_DERIVED_COMPONENT_CONTRACT_NOT_MAPPED.value,
                index=index,
                dtype="object",
            ),
        )

    state = legacy_bool.astype(bool).map(
        lambda value: TriState.TRUE.value if value else TriState.FALSE.value
    )
    return state, pd.Series(
        RsiComputabilityReason.OK.value,
        index=index,
        dtype="object",
    )


def strict_ranking_for_component(
    *,
    panel: pd.DataFrame,
    spec: ComponentSpec,
    legacy_values: pd.Series,
    cache: FeatureCache,
    signal_context,
    computability_context: SignalComputabilityContext,
) -> tuple[pd.Series, pd.Series]:
    component_type = str(spec.type).upper()
    if component_type != "RSI":
        return legacy_values.copy(), pd.Series(
            RsiComputabilityReason.OK.value,
            index=panel.index,
            dtype="object",
        )

    lookback = int(spec.params.get("lookback", 14))
    values = rsi_values(
        panel=panel,
        lookback=lookback,
        cache=cache,
        signal_context=signal_context,
    )
    availability = rsi_value_availability(
        panel,
        lookback=lookback,
        context=computability_context,
        diagnostic_rsi=values,
    )
    strict_values = legacy_values.where(
        availability["computable"],
        np.nan,
    )
    return strict_values, availability["reason"].astype("object")
