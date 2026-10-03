from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import numpy as np
import pandas as pd


FORMULA_VERSION = "layer1_60d_ma120_causal_raw_v2"
PRICE_COORDINATE = "CAUSAL_RAW_V2"


class CausalRawV2Error(ValueError):
    pass


class CoordinateStatus(str, Enum):
    READY = "READY"
    EVENT_NOT_YET_KNOWN = "EVENT_NOT_YET_KNOWN"
    EVENT_KNOWN_AT_UNKNOWN = "EVENT_KNOWN_AT_UNKNOWN"
    EVENT_TRANSFORM_NONPOSITIVE = "EVENT_TRANSFORM_NONPOSITIVE"


class FeatureState(str, Enum):
    READY = "READY"
    WARMUP_INSUFFICIENT = "WARMUP_INSUFFICIENT"
    INPUT_MISSING = "INPUT_MISSING"
    CA_COORDINATE_BLOCKED = "CA_COORDINATE_BLOCKED"


@dataclass(frozen=True)
class CausalRawV2Parameters:
    ma_window: int = 120
    breakout_lookback: int = 60
    liquidity_lookback: int = 20

    def __post_init__(self) -> None:
        frozen = (120, 60, 20)
        actual = (self.ma_window, self.breakout_lookback, self.liquidity_lookback)
        if actual != frozen:
            raise CausalRawV2Error(
                "causal RAW v2 parameters are frozen at MA120/N60/prior20; "
                f"got {actual}"
            )


def _normalize_panel(panel: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "stock_id",
        "raw_close",
        "Trading_money",
        "observed_trade",
        "valid_ohlc",
        "decision_cutoff_at",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise CausalRawV2Error(f"causal RAW v2 panel missing columns: {missing}")

    out = panel.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["stock_id"] = out["stock_id"].astype(str)
    out["raw_close"] = pd.to_numeric(out["raw_close"], errors="coerce")
    out["Trading_money"] = pd.to_numeric(out["Trading_money"], errors="coerce")
    out["decision_cutoff_at"] = pd.to_datetime(
        out["decision_cutoff_at"], errors="coerce"
    )
    if out[["date", "stock_id", "decision_cutoff_at"]].isna().any(axis=1).any():
        raise CausalRawV2Error(
            "date, stock_id, and decision_cutoff_at must be explicit and non-null"
        )
    if out.duplicated(["date", "stock_id"]).any():
        raise CausalRawV2Error("causal RAW v2 panel has duplicate logical keys")

    out["observed_trade"] = out["observed_trade"].fillna(False).astype(bool)
    out["valid_ohlc"] = out["valid_ohlc"].fillna(False).astype(bool)
    return out.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)


def normalize_event_groups(events: pd.DataFrame) -> pd.DataFrame:
    """Collapse approved cash/share components into one economic event-date transform.

    Input is the output shape of ``normalized_actions_frame``.  Only the already
    approved CASH_DIVIDEND and STOCK_DIVIDEND component semantics are accepted.
    Same-date components are combined as ``P_post = (P_pre - cash) / multiplier``.
    No price-derived ratio, date inference, or rounding is performed here.
    """

    required = {
        "stock_id",
        "effective_date",
        "event_kind",
        "known_at",
        "cash_per_share",
        "share_multiplier",
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise CausalRawV2Error(f"causal RAW v2 events missing columns: {missing}")

    if events.empty:
        return pd.DataFrame(
            columns=[
                "stock_id",
                "effective_date",
                "known_at",
                "cash_per_share",
                "share_multiplier",
                "event_components",
            ]
        )

    x = events.copy().reset_index(drop=True)
    x["stock_id"] = x["stock_id"].astype(str)
    x["effective_date"] = pd.to_datetime(
        x["effective_date"], errors="coerce"
    ).dt.normalize()
    x["known_at"] = pd.to_datetime(x["known_at"], errors="coerce")
    x["cash_per_share"] = pd.to_numeric(x["cash_per_share"], errors="coerce")
    x["share_multiplier"] = pd.to_numeric(
        x["share_multiplier"], errors="coerce"
    )
    if {"source_name", "source_row"}.issubset(x.columns):
        identity = [
            "stock_id", "effective_date", "event_kind", "source_name", "source_row"
        ]
        if x.duplicated(identity).any():
            raise CausalRawV2Error(
                "duplicate normalized corporate-action component identity"
            )
    if x[["stock_id", "effective_date"]].isna().any(axis=1).any():
        raise CausalRawV2Error("events require non-null stock_id and effective_date")

    allowed = {"CASH_DIVIDEND", "STOCK_DIVIDEND"}
    bad_kind = sorted(set(x["event_kind"].astype(str)) - allowed)
    if bad_kind:
        raise CausalRawV2Error(
            "unsupported event_kind for causal RAW v2: " + ", ".join(bad_kind)
        )

    cash_rows = x["event_kind"].eq("CASH_DIVIDEND")
    stock_rows = x["event_kind"].eq("STOCK_DIVIDEND")
    if (
        x.loc[cash_rows, "cash_per_share"].isna()
        | x.loc[cash_rows, "cash_per_share"].le(0)
    ).any():
        raise CausalRawV2Error("CASH_DIVIDEND requires positive cash_per_share")
    if (
        x.loc[stock_rows, "share_multiplier"].isna()
        | x.loc[stock_rows, "share_multiplier"].le(0)
    ).any():
        raise CausalRawV2Error("STOCK_DIVIDEND requires positive share_multiplier")

    rows: list[dict[str, object]] = []
    for (ticker, effective_date), g in x.groupby(
        ["stock_id", "effective_date"], sort=True
    ):
        known_complete = g["known_at"].notna().all()
        known_at = g["known_at"].max() if known_complete else pd.NaT
        cash = float(g.loc[g["event_kind"].eq("CASH_DIVIDEND"), "cash_per_share"].sum())
        multipliers = g.loc[
            g["event_kind"].eq("STOCK_DIVIDEND"), "share_multiplier"
        ].dropna()
        multiplier = float(multipliers.prod()) if len(multipliers) else 1.0
        if cash < 0 or multiplier <= 0:
            raise CausalRawV2Error("invalid aggregated corporate-action economics")
        rows.append(
            {
                "stock_id": str(ticker),
                "effective_date": pd.Timestamp(effective_date).normalize(),
                "known_at": known_at,
                "cash_per_share": cash,
                "share_multiplier": multiplier,
                "event_components": int(len(g)),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["stock_id", "effective_date"], kind="stable"
    ).reset_index(drop=True)


def raw_universe_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Return the existing UniverseCompiler input with RAW absolute close.

    This is intentionally only a coordinate adapter: it does not alter any
    universe threshold, turnover ranking, P2-060 exclusion, or tradability rule.
    Decision-cutoff evidence is deliberately not required merely to construct
    this adapter; the strategy-availability gate remains a separate fail-closed
    contract.
    """

    columns = [
        "date", "stock_id", "raw_close", "Trading_money",
        "observed_trade", "valid_ohlc",
    ]
    missing = sorted(set(columns) - set(panel.columns))
    if missing:
        raise CausalRawV2Error(f"RAW universe panel missing columns: {missing}")
    out = panel[columns].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["stock_id"] = out["stock_id"].astype(str)
    out["raw_close"] = pd.to_numeric(out["raw_close"], errors="coerce")
    out["Trading_money"] = pd.to_numeric(out["Trading_money"], errors="coerce")
    out["observed_trade"] = out["observed_trade"].fillna(False).astype(bool)
    out["valid_ohlc"] = out["valid_ohlc"].fillna(False).astype(bool)
    if out[["date", "stock_id"]].isna().any(axis=1).any():
        raise CausalRawV2Error("RAW universe panel has null logical keys")
    if out.duplicated(["date", "stock_id"]).any():
        raise CausalRawV2Error("RAW universe panel has duplicate logical keys")
    out = out.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)
    return out.rename(columns={"raw_close": "close"})


def _all_finite(values: Iterable[float]) -> bool:
    return all(np.isfinite(float(x)) for x in values)


def _state_for_window(
    *,
    coordinate_status: CoordinateStatus,
    rows_available: int,
    rows_required: int,
    values: Iterable[float],
) -> FeatureState:
    if coordinate_status is not CoordinateStatus.READY:
        return FeatureState.CA_COORDINATE_BLOCKED
    if rows_available < rows_required:
        return FeatureState.WARMUP_INSUFFICIENT
    if not _all_finite(values):
        return FeatureState.INPUT_MISSING
    return FeatureState.READY


def build_causal_raw_v2_features(
    panel: pd.DataFrame,
    events: pd.DataFrame,
    *,
    params: CausalRawV2Parameters | None = None,
) -> pd.DataFrame:
    """Build the minimal causal RAW-v2 layer on a common-session panel.

    The panel must already retain one row per relevant market session within a
    ticker's active span.  Missing/suspended sessions stay as null rows and are
    never compressed out of rolling windows.

    Earlier feature outputs are immutable.  When a corporate action becomes both
    effective and known before the row's explicit decision cutoff, only the
    in-memory historical observations strictly before that effective date are
    transformed into the event's post-event RAW coordinate.  Current/future RAW
    observations are never rewritten.  An effective but not-yet-known event
    blocks technical comparability until it becomes known.
    """

    p = params or CausalRawV2Parameters()
    work = _normalize_panel(panel)
    grouped_events = normalize_event_groups(events)
    event_map = {
        ticker: g.reset_index(drop=True)
        for ticker, g in grouped_events.groupby("stock_id", sort=False)
    }

    rows: list[dict[str, object]] = []
    for ticker, g in work.groupby("stock_id", sort=False):
        g = g.reset_index(drop=True)
        ev = event_map.get(str(ticker), pd.DataFrame())
        event_pos = 0
        history_dates: list[pd.Timestamp] = []
        history_close: list[float] = []
        amount_history: list[float] = []
        session_rows_seen = 0
        max_price_history = max(p.ma_window - 1, p.breakout_lookback + 1)
        cumulative_event_groups = 0

        for r in g.itertuples(index=False):
            date = pd.Timestamp(r.date).normalize()
            cutoff = pd.Timestamp(r.decision_cutoff_at)
            coordinate_status = CoordinateStatus.READY
            event_groups_applied = 0

            while event_pos < len(ev):
                event = ev.iloc[event_pos]
                effective = pd.Timestamp(event["effective_date"]).normalize()
                if effective > date:
                    break
                known_at = event["known_at"]
                if pd.isna(known_at):
                    coordinate_status = CoordinateStatus.EVENT_KNOWN_AT_UNKNOWN
                    break
                if pd.Timestamp(known_at) >= cutoff:
                    coordinate_status = CoordinateStatus.EVENT_NOT_YET_KNOWN
                    break

                cash = float(event["cash_per_share"])
                multiplier = float(event["share_multiplier"])
                affected = [
                    i for i, d in enumerate(history_dates) if d < effective
                ]
                transformed: dict[int, float] = {}
                invalid = False
                for i in affected:
                    value = history_close[i]
                    if not np.isfinite(value):
                        continue
                    candidate = (float(value) - cash) / multiplier
                    if not np.isfinite(candidate) or candidate <= 0:
                        invalid = True
                        break
                    transformed[i] = candidate
                if invalid:
                    coordinate_status = CoordinateStatus.EVENT_TRANSFORM_NONPOSITIVE
                    break

                for i, value in transformed.items():
                    history_close[i] = value
                event_pos += 1
                event_groups_applied += 1
                cumulative_event_groups += 1

            raw_close = float(r.raw_close) if pd.notna(r.raw_close) else np.nan
            current_valid = (
                bool(r.observed_trade)
                and bool(r.valid_ohlc)
                and np.isfinite(raw_close)
                and raw_close > 0
            )
            current_close = raw_close if current_valid else np.nan

            ma_values = [*history_close[-(p.ma_window - 1):], current_close]
            ma_state = _state_for_window(
                coordinate_status=coordinate_status,
                rows_available=len(history_close) + 1,
                rows_required=p.ma_window,
                values=ma_values,
            )
            if ma_state is FeatureState.READY:
                ma120 = float(np.mean(ma_values))
                close_to_ma120 = current_close / ma120 - 1.0 if ma120 > 0 else np.nan
                if not np.isfinite(close_to_ma120):
                    ma_state = FeatureState.INPUT_MISSING
                    ma120 = np.nan
                    close_to_ma120 = np.nan
            else:
                ma120 = np.nan
                close_to_ma120 = np.nan

            n_required_history = p.breakout_lookback + 1
            n_values = history_close[-n_required_history:]
            n_state = _state_for_window(
                coordinate_status=coordinate_status,
                rows_available=len(history_close),
                rows_required=n_required_history,
                values=[*n_values, current_close],
            )
            prior_high = np.nan
            previous_prior_high = np.nan
            n60_value: object = pd.NA
            if n_state is FeatureState.READY:
                prior_window = history_close[-p.breakout_lookback:]
                previous_prior_window = history_close[-(p.breakout_lookback + 1):-1]
                prior_high = float(np.max(prior_window))
                previous_prior_high = float(np.max(previous_prior_window))
                previous_close = float(history_close[-1])
                n60_value = bool(
                    current_close > prior_high
                    and previous_close <= previous_prior_high
                )

            amount_window = amount_history[-p.liquidity_lookback:]
            if len(amount_history) < p.liquidity_lookback:
                amount_state = FeatureState.WARMUP_INSUFFICIENT
                prior20_amount = np.nan
            elif not _all_finite(amount_window):
                amount_state = FeatureState.INPUT_MISSING
                prior20_amount = np.nan
            else:
                amount_state = FeatureState.READY
                prior20_amount = float(np.mean(amount_window))

            rows.append(
                {
                    "date": date,
                    "stock_id": str(ticker),
                    "decision_cutoff_at": cutoff,
                    "raw_close_twd": raw_close,
                    "causal_close": current_close,
                    "price_coordinate": PRICE_COORDINATE,
                    "formula_version": FORMULA_VERSION,
                    "coordinate_status": coordinate_status.value,
                    "event_groups_applied": event_groups_applied,
                    "event_groups_applied_cumulative": cumulative_event_groups,
                    "ma120": ma120,
                    "close_to_ma120": close_to_ma120,
                    "ma120_state": ma_state.value,
                    "ma120_comparable": ma_state is FeatureState.READY,
                    "prior_high60": prior_high,
                    "previous_prior_high60": previous_prior_high,
                    "n60_first_cross": n60_value,
                    "n60_state": n_state.value,
                    "n60_comparable": n_state is FeatureState.READY,
                    "prior20_amount_twd": prior20_amount,
                    "prior20_amount_state": amount_state.value,
                    "bars_seen": session_rows_seen + 1,
                }
            )

            history_dates.append(date)
            history_close.append(current_close)
            if len(history_close) > max_price_history:
                del history_close[0]
                del history_dates[0]
            current_amount = (
                float(r.Trading_money) if pd.notna(r.Trading_money) else np.nan
            )
            amount_history.append(current_amount)
            if len(amount_history) > p.liquidity_lookback:
                del amount_history[0]
            session_rows_seen += 1

    out = pd.DataFrame(rows)
    if not out.empty:
        out["n60_first_cross"] = pd.array(out["n60_first_cross"], dtype="boolean")
    return out
