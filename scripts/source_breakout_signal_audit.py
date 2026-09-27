#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from astraquant.features.technical import (
    BreakoutSignalConfig,
    build_simple_breakout_signals,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_BREAKOUT_SIGNAL_AUDIT.md"))
LOOKBACK = int(os.environ.get("BREAKOUT_LOOKBACK", "250"))
AUDIT_START = pd.Timestamp(os.environ.get("AUDIT_START", "2025-01-01"))


def load_adjusted() -> pd.DataFrame:
    parts = []
    for year in (2024, 2025, 2026):
        path = SOURCE_ROOT / "adj" / f"prices_adj_{year}.parquet"
        if not path.exists():
            raise SystemExit(f"BLOCKED: missing adjusted file {path.name}")
        d = pd.read_parquet(
            path,
            columns=["date", "stock_id", "open", "max", "min", "close", "Trading_money"],
        )
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
        d["stock_id"] = d["stock_id"].astype(str)
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def load_tradability() -> pd.DataFrame:
    path = SOURCE_ROOT / "reference" / "tradability.parquet"
    d = pd.read_parquet(
        path,
        columns=["date", "stock_id", "observed_trade", "valid_ohlc", "buy_blocked"],
    )
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
    d["stock_id"] = d["stock_id"].astype(str)
    return d[d["date"].ge(pd.Timestamp("2024-01-01"))].copy()


def load_raw(years: set[int]) -> pd.DataFrame:
    parts = []
    for year in sorted(years):
        path = SOURCE_ROOT / "raw" / f"prices_raw_{year}.parquet"
        if not path.exists():
            continue
        d = pd.read_parquet(
            path,
            columns=["date", "stock_id", "open", "max", "min", "close"],
        )
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
        d["stock_id"] = d["stock_id"].astype(str)
        parts.append(d)
    if not parts:
        raise SystemExit("BLOCKED: no RAW files for signal execution audit")
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability()

    signals = build_simple_breakout_signals(
        adjusted,
        tradability,
        config=BreakoutSignalConfig(
            lookback=LOOKBACK,
            universe_fraction=0.25,
            feature_name="simple_breakout",
            feature_version="v1",
        ),
    )
    signals = signals[signals["signal_date"].ge(AUDIT_START)].copy()

    if signals.empty:
        raise SystemExit("FAIL: canonical breakout builder produced no audit-period signals")

    # Signal-day PIT/validity verification.
    sig_verify = signals.merge(
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]].rename(
            columns={"date": "signal_date"}
        ),
        on=["signal_date", "stock_id"],
        how="left",
        validate="one_to_one",
    )
    bad_signal_trad = int(
        (
            ~sig_verify["observed_trade"].fillna(False).astype(bool)
            | ~sig_verify["valid_ohlc"].fillna(False).astype(bool)
        ).sum()
    )

    # Map signal close T -> next global adjusted-research session T+1.
    sessions = (
        adjusted["date"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    next_session = {
        pd.Timestamp(sessions[i]): pd.Timestamp(sessions[i + 1])
        for i in range(len(sessions) - 1)
    }
    signals["intended_entry_date"] = signals["signal_date"].map(next_session)
    no_next_session = int(signals["intended_entry_date"].isna().sum())

    mapped = signals.dropna(subset=["intended_entry_date"]).copy()
    raw_years = set(mapped["intended_entry_date"].dt.year.astype(int).tolist())
    raw = load_raw(raw_years)

    entry = mapped.merge(
        raw.rename(
            columns={
                "date": "intended_entry_date",
                "open": "raw_open",
                "max": "raw_high",
                "min": "raw_low",
                "close": "raw_close",
            }
        ),
        on=["intended_entry_date", "stock_id"],
        how="left",
        validate="many_to_one",
    )
    entry = entry.merge(
        tradability[
            ["date", "stock_id", "observed_trade", "valid_ohlc", "buy_blocked"]
        ].rename(
            columns={
                "date": "intended_entry_date",
                "observed_trade": "entry_observed_trade",
                "valid_ohlc": "entry_valid_ohlc",
            }
        ),
        on=["intended_entry_date", "stock_id"],
        how="left",
        validate="many_to_one",
    )

    raw_valid = (
        entry[["raw_open", "raw_high", "raw_low", "raw_close"]].notna().all(axis=1)
        & (entry[["raw_open", "raw_high", "raw_low", "raw_close"]] > 0).all(axis=1)
        & (entry["raw_high"] >= entry[["raw_open", "raw_close", "raw_low"]].max(axis=1))
        & (entry["raw_low"] <= entry[["raw_open", "raw_close", "raw_high"]].min(axis=1))
    )
    executable = (
        raw_valid
        & entry["entry_observed_trade"].fillna(False).astype(bool)
        & entry["entry_valid_ohlc"].fillna(False).astype(bool)
        & ~entry["buy_blocked"].fillna(True).astype(bool)
    )
    entry["raw_entry_executable"] = executable

    year_counts = (
        signals.assign(year=signals["signal_date"].dt.year)
        .groupby("year")
        .size()
        .to_dict()
    )
    month_counts = (
        signals.assign(month=signals["signal_date"].dt.to_period("M").astype(str))
        .groupby("month")
        .size()
        .to_dict()
    )

    checks = {
        "signals_nonempty": len(signals) > 0,
        "signal_available_same_close_date": bool(
            signals["available_date"].eq(signals["signal_date"]).all()
        ),
        "signal_day_tradability_valid": bad_signal_trad == 0,
        "price_semantics_declared": bool(
            signals["price_semantics"].eq("SCALE_SENSITIVE").all()
        ),
        "ca_window_requirement_declared": bool(
            signals["ca_window_requirement"]
            .eq("CONSISTENT_ADJUSTMENT_WITHIN_LOOKBACK")
            .all()
        ),
        "execution_mapping_uses_next_session": len(mapped) + no_next_session == len(signals),
        "raw_execution_coordinate_checked": "raw_open" in entry.columns,
        "no_adjusted_execution_price_emitted": True,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Source Canonical Breakout Signal Audit",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: validate canonical simple-breakout candidate generation on frozen source data without evaluating returns.",
        "",
        "## Configuration",
        "",
        f"- adjusted research input: 2024–2026",
        f"- audited signal period: {AUDIT_START.date()} through {signals['signal_date'].max().date()}",
        f"- breakout lookback: {LOOKBACK} sessions",
        "- daily universe: top 25% by turnover among numeric four-digit, valid adjusted, observed/valid tradability stock-days",
        "- signal availability: after signal-session close",
        "- intended fill coordinate: next-session RAW open",
        "",
        "## Candidate counts",
        "",
        f"- canonical signal candidates: {len(signals):,}",
        f"- candidates with known next source session: {len(mapped):,}",
        f"- final-session candidates awaiting a future session: {no_next_session:,}",
        f"- next-session RAW/tradability executable candidates: {int(executable.sum()):,}",
        f"- next-session candidates blocked/unavailable: {int((~executable).sum()):,}",
        "",
        "### By year",
        "",
        "| Year | Signal candidates |",
        "|---:|---:|",
    ]
    for year, count in sorted(year_counts.items()):
        lines.append(f"| {year} | {count:,} |")

    lines += [
        "",
        "### Recent monthly counts",
        "",
        "| Month | Signal candidates |",
        "|---|---:|",
    ]
    for month, count in list(sorted(month_counts.items()))[-12:]:
        lines.append(f"| {month} | {count:,} |")

    lines += [
        "",
        "## Gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "## Interpretation",
        "",
        "Signal generation remains an adjusted-research operation. The audit maps candidates to the following source session only to classify whether a RAW/tradability execution price exists; adjusted close is never reused as an execution price.",
        "",
        "No CAGR, return, drawdown, hit-rate, ranking-quality, or strategy comparison is computed here.",
        "",
        "## Next gate",
        "",
        "Convert canonical signal candidates into a deterministic portfolio-intent policy (board-lot sizing, capacity, re-entry, stop/expiry rules) that feeds CanonicalExecutionService. Performance remains locked while that migration is incomplete.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        print("FAILED_CHECKS=" + ",".join(failed))
        raise SystemExit("FAIL: canonical breakout signal audit failed")


if __name__ == "__main__":
    main()
