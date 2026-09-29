from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pandas as pd

from astraquant.research.vcp_round1 import (
    ConfigTradeSimulation,
    VCPRound1TradeRunner,
)
from astraquant.research.vcp_round1_reporting import summary_row


ROUND2_MIN_AMPLITUDE_3 = 0.01
ENTRY_LIQUIDITY_LOOKBACK = 20


def build_entry_liquidity_features(
    common_panel: pd.DataFrame,
    *,
    lookback: int = ENTRY_LIQUIDITY_LOOKBACK,
) -> pd.DataFrame:
    """Build descriptive entry-date liquidity fields without filling missing data.

    The prior average uses exactly the preceding common-session rows for each
    ticker and excludes the entry day. entry_day_amount_twd is a descriptive
    same-day observation available only after that session completes; it is not
    an entry-decision input.
    """
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    required = {"date", "stock_id", "Trading_money"}
    missing = required - set(common_panel.columns)
    if missing:
        raise ValueError(
            f"entry liquidity panel missing columns: {sorted(missing)}"
        )

    x = common_panel[["date", "stock_id", "Trading_money"]].copy()
    x["date"] = pd.to_datetime(x["date"], errors="coerce").dt.normalize()
    x["stock_id"] = x["stock_id"].astype(str)
    x["entry_day_amount_twd"] = pd.to_numeric(
        x["Trading_money"], errors="coerce"
    )
    x = x.sort_values(["stock_id", "date"], kind="stable").reset_index(
        drop=True
    )
    x["entry_prior_avg_amount_twd"] = x.groupby(
        "stock_id", sort=False
    )["entry_day_amount_twd"].transform(
        lambda s: s.shift(1).rolling(
            lookback, min_periods=lookback
        ).mean()
    )
    x["entry_prior_avg_amount_missing_reason"] = np.where(
        x["entry_prior_avg_amount_twd"].isna(),
        f"MISSING_PRIOR_{lookback}_COMMON_SESSION_AMOUNT",
        "",
    )
    x["entry_day_amount_missing_reason"] = np.where(
        x["entry_day_amount_twd"].isna(),
        "MISSING_ENTRY_DAY_AMOUNT",
        "",
    )
    return x[
        [
            "date",
            "stock_id",
            "entry_prior_avg_amount_twd",
            "entry_day_amount_twd",
            "entry_prior_avg_amount_missing_reason",
            "entry_day_amount_missing_reason",
        ]
    ]


def _liquidity_lookup(
    features: pd.DataFrame,
) -> dict[tuple[str, str], dict[str, object]]:
    required = {
        "date",
        "stock_id",
        "entry_prior_avg_amount_twd",
        "entry_day_amount_twd",
        "entry_prior_avg_amount_missing_reason",
        "entry_day_amount_missing_reason",
    }
    missing = required - set(features.columns)
    if missing:
        raise ValueError(
            f"entry liquidity features missing columns: {sorted(missing)}"
        )
    lookup: dict[tuple[str, str], dict[str, object]] = {}
    for row in features.itertuples(index=False):
        key = (
            str(row.stock_id),
            pd.Timestamp(row.date).date().isoformat(),
        )
        if key in lookup:
            raise ValueError(f"duplicate entry liquidity key: {key}")
        lookup[key] = {
            "entry_prior_avg_amount_twd": row.entry_prior_avg_amount_twd,
            "entry_day_amount_twd": row.entry_day_amount_twd,
            "entry_prior_avg_amount_missing_reason": (
                row.entry_prior_avg_amount_missing_reason
            ),
            "entry_day_amount_missing_reason": (
                row.entry_day_amount_missing_reason
            ),
        }
    return lookup


def enrich_entry_liquidity(
    frame: pd.DataFrame,
    *,
    features: pd.DataFrame,
) -> pd.DataFrame:
    """Attach round2 entry liquidity diagnostics to trade/open rows."""
    out = frame.copy()
    cols = [
        "entry_prior_avg_amount_twd",
        "entry_day_amount_twd",
        "entry_prior_avg_amount_missing_reason",
        "entry_day_amount_missing_reason",
    ]
    if out.empty:
        for col in cols:
            out[col] = pd.Series(dtype=object)
        return out
    required = {"stock_id", "entry_date"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(
            f"trade frame missing entry keys: {sorted(missing)}"
        )
    lookup = _liquidity_lookup(features)
    attached: list[dict[str, object]] = []
    for row in out[["stock_id", "entry_date"]].itertuples(index=False):
        key = (
            str(row.stock_id),
            pd.Timestamp(row.entry_date).date().isoformat(),
        )
        hit = lookup.get(key)
        if hit is None:
            hit = {
                "entry_prior_avg_amount_twd": np.nan,
                "entry_day_amount_twd": np.nan,
                "entry_prior_avg_amount_missing_reason": (
                    "ENTRY_LIQUIDITY_ROW_MISSING"
                ),
                "entry_day_amount_missing_reason": (
                    "ENTRY_LIQUIDITY_ROW_MISSING"
                ),
            }
        attached.append(hit)
    extra = pd.DataFrame(attached, index=out.index)
    for col in cols:
        out[col] = extra[col]
    return out


class VCPRound2TradeRunner(VCPRound1TradeRunner):
    """Round2 adapter; round1 execution behavior remains untouched."""

    def __init__(
        self,
        *,
        entry_liquidity_features: pd.DataFrame,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.entry_liquidity_features = entry_liquidity_features.copy()

    def simulate_config(self, *args, **kwargs) -> ConfigTradeSimulation:
        base = super().simulate_config(*args, **kwargs)
        return replace(
            base,
            trades=enrich_entry_liquidity(
                base.trades,
                features=self.entry_liquidity_features,
            ),
            open_positions=enrich_entry_liquidity(
                base.open_positions,
                features=self.entry_liquidity_features,
            ),
        )


def round2_exit_reason_counts(
    simulation: ConfigTradeSimulation,
) -> dict[str, int]:
    reasons = (
        simulation.trades["exit_reason"].astype(str)
        if not simulation.trades.empty
        else pd.Series(dtype=str)
    )
    atr = int(reasons.eq("ATR").sum())
    ma21 = int(reasons.eq("D21").sum())
    both = int(reasons.eq("BOTH").sum())
    terminal = int(reasons.str.startswith("TERMINAL:").sum())
    known = atr + ma21 + both + terminal
    if known != len(reasons):
        unknown = sorted(
            set(reasons)
            - {"ATR", "D21", "BOTH"}
            - {
                x
                for x in set(reasons)
                if str(x).startswith("TERMINAL:")
            }
        )
        raise ValueError(
            f"unclassified round2 exit reasons: {unknown}"
        )
    open_count = int(len(simulation.open_positions))
    total = atr + ma21 + both + terminal + open_count
    expected = int(len(reasons) + len(simulation.open_positions))
    if total != expected:
        raise ValueError(
            f"exit distribution identity failed: {total} != {expected}"
        )
    return {
        "exit_atr_count": atr,
        "exit_ma21_count": ma21,
        "exit_both_count": both,
        "exit_open_count": open_count,
        "exit_terminal_count": terminal,
    }


def round2_summary_row(
    *,
    config_id: str,
    params: dict[str, object],
    simulation: ConfigTradeSimulation,
    low_n_threshold: int,
) -> dict[str, object]:
    row = summary_row(
        config_id=config_id,
        params=params,
        simulation=simulation,
        low_n_threshold=low_n_threshold,
    )
    row.update(round2_exit_reason_counts(simulation))
    category_total = sum(
        int(row[name])
        for name in (
            "exit_atr_count",
            "exit_ma21_count",
            "exit_both_count",
            "exit_open_count",
            "exit_terminal_count",
        )
    )
    expected = int(row["n_closed"]) + int(row["n_open"])
    if category_total != expected:
        raise ValueError(
            "round2 summary exit-count identity failed: "
            f"{category_total} != {expected}"
        )
    return row
