from __future__ import annotations

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.execution.service import SignalDeclaration

REQUIRED_CANDIDATE_COLUMNS = (
    "signal_date",
    "stock_id",
    "signal_source",
    "signal_price_semantics",
    "available_at",
)


def _end_of_signal_day(value: object) -> pd.Timestamp:
    day = pd.Timestamp(value).normalize()
    return day + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)


def candidates_from_signal_frame(
    frame: pd.DataFrame,
    *,
    declaration: SignalDeclaration,
    candidate_mask_column: str | None = "counts_as_candidate",
) -> pd.DataFrame:
    """Convert research signal output into the canonical candidate contract.

    Daily research signals default to conservative end-of-signal-day availability.
    If the frame carries an explicit available_at column it is preserved.
    """
    required = {"signal_date", "stock_id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"candidate source missing columns: {sorted(missing)}")

    work = frame.copy()
    if candidate_mask_column is not None:
        if candidate_mask_column not in work.columns:
            raise ValueError(f"candidate mask column missing: {candidate_mask_column}")
        work = work[work[candidate_mask_column].fillna(False).astype(bool)].copy()

    keep_optional = [c for c in ("turnover_value", "breakout_excess") if c in work.columns]
    out = work[["signal_date", "stock_id", *keep_optional]].copy()
    out["signal_source"] = declaration.source
    out["signal_price_semantics"] = declaration.price_semantics.value
    if "available_at" in work.columns:
        out["available_at"] = pd.to_datetime(
            work.loc[out.index, "available_at"], errors="coerce"
        )
    else:
        out["available_at"] = out["signal_date"].map(_end_of_signal_day)
    return normalize_candidates(out)


def legacy_signals_to_candidates(
    signals: pd.DataFrame,
    *,
    declaration: SignalDeclaration,
) -> pd.DataFrame:
    """Compatibility adapter for the frozen breakout-builder DataFrame."""
    return candidates_from_signal_frame(
        signals,
        declaration=declaration,
        candidate_mask_column=None,
    )


def normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    missing = set(REQUIRED_CANDIDATE_COLUMNS) - set(candidates.columns)
    if missing:
        raise ValueError(f"candidates missing columns: {sorted(missing)}")

    optional = [c for c in ("turnover_value", "breakout_excess") if c in candidates.columns]
    out = candidates[[*REQUIRED_CANDIDATE_COLUMNS, *optional]].copy()
    out["signal_date"] = pd.to_datetime(out["signal_date"], errors="coerce").dt.normalize()
    out["stock_id"] = out["stock_id"].astype(str)
    out["signal_source"] = out["signal_source"].astype(str)
    out["signal_price_semantics"] = out["signal_price_semantics"].astype(str)
    out["available_at"] = pd.to_datetime(out["available_at"], errors="coerce")

    if out[list(REQUIRED_CANDIDATE_COLUMNS)].isna().any(axis=1).any():
        raise ValueError("candidates contain null required fields")
    if (out["signal_source"].str.strip() == "").any():
        raise ValueError("candidate signal_source must be declared")
    allowed = {x.value for x in SignalPriceSemantics}
    invalid_semantics = sorted(set(out["signal_price_semantics"]) - allowed)
    if invalid_semantics:
        raise ValueError(f"unsupported signal_price_semantics: {invalid_semantics}")
    if (out["available_at"] < out["signal_date"]).any():
        raise ValueError("candidate available_at cannot precede signal_date")
    if out.duplicated(["signal_date", "stock_id"]).any():
        raise ValueError("candidates contain duplicate (signal_date, stock_id)")
    return out.sort_values(["signal_date", "stock_id"], kind="stable").reset_index(drop=True)


def declaration_from_candidate(row: dict[str, object]) -> SignalDeclaration:
    return SignalDeclaration(
        source=str(row["signal_source"]),
        price_semantics=SignalPriceSemantics(str(row["signal_price_semantics"])),
    )
