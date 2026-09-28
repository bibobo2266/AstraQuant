#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.features.technical import BreakoutSignalConfig, build_simple_breakout_signals
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationConfig

from source_strategy_integration_smoke import (
    DRAIN_SESSIONS,
    SIGNAL_END,
    SIGNAL_START,
    build_supported_ca,
    load_adjusted,
    load_tradability,
    pit_unsafe_ca_tickers,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_MATCHED_PLACEBO.md"))
INITIAL_CASH = 10_000_000.0
COMMON_SUPPORT_EXCLUDED_TICKERS = {"2823"}
SEEDS = (101, 202, 303)


def _metrics(nav: pd.Series) -> dict[str, float]:
    daily = nav.pct_change().dropna()
    elapsed_years = (nav.index[-1] - nav.index[0]).days / 365.2425
    total_return = nav.iloc[-1] / INITIAL_CASH - 1.0
    cagr = (nav.iloc[-1] / INITIAL_CASH) ** (1.0 / elapsed_years) - 1.0
    dd = nav / nav.cummax() - 1.0
    sharpe = (
        float(daily.mean() / daily.std(ddof=1) * math.sqrt(252))
        if len(daily) > 1 and daily.std(ddof=1) > 0
        else float("nan")
    )
    return {
        "final_nav": float(nav.iloc[-1]),
        "total_return": float(total_return),
        "cagr": float(cagr),
        "max_drawdown": float(dd.min()),
        "sharpe": sharpe,
    }


def _eligible_turnover_universe(
    adjusted: pd.DataFrame,
    tradability: pd.DataFrame,
    excluded: set[str],
) -> pd.DataFrame:
    adj = adjusted.copy()
    trad = tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]].copy()
    merged = adj.merge(
        trad,
        on=["date", "stock_id"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    numeric_id = merged["stock_id"].astype(str).str.fullmatch(r"[1-9]\d{3}", na=False)
    positive = (merged[["open", "max", "min", "close"]] > 0).all(axis=1)
    geometry = (
        merged["max"] >= merged[["open", "close", "min"]].max(axis=1)
    ) & (
        merged["min"] <= merged[["open", "close", "max"]].min(axis=1)
    )
    valid_turnover = pd.to_numeric(
        merged["Trading_money"], errors="coerce"
    ).gt(0)
    tradable = (
        merged["_merge"].eq("both")
        & merged["observed_trade"].fillna(False).astype(bool)
        & merged["valid_ohlc"].fillna(False).astype(bool)
    )
    eligible = merged[
        numeric_id & positive & geometry & valid_turnover & tradable
    ].copy()
    eligible["turnover_percentile"] = eligible.groupby("date")["Trading_money"].rank(
        pct=True,
        ascending=False,
        method="average",
    )
    eligible = eligible[
        eligible["turnover_percentile"].le(0.25)
        & eligible["date"].between(SIGNAL_START, SIGNAL_END)
        & ~eligible["stock_id"].astype(str).isin(excluded)
    ].copy()
    return eligible[["date", "stock_id"]].drop_duplicates()


def _matched_random_signals(
    *,
    baseline: pd.DataFrame,
    eligible: pd.DataFrame,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    baseline_by_day = {
        pd.Timestamp(day): set(group["stock_id"].astype(str))
        for day, group in baseline.groupby("signal_date")
    }
    eligible_by_day = {
        pd.Timestamp(day): sorted(set(group["stock_id"].astype(str)))
        for day, group in eligible.groupby("date")
    }

    rows: list[dict[str, object]] = []
    for day, base_tickers in sorted(baseline_by_day.items()):
        pool = [x for x in eligible_by_day.get(day, []) if x not in base_tickers]
        n = len(base_tickers)
        if len(pool) < n:
            pool = eligible_by_day.get(day, [])
        if len(pool) < n:
            raise SystemExit(
                f"BLOCKED: insufficient matched placebo pool on {day.date()}: "
                f"need {n}, have {len(pool)}"
            )
        chosen = rng.choice(np.array(pool, dtype=object), size=n, replace=False)
        for ticker in sorted(str(x) for x in chosen):
            rows.append({"signal_date": day, "stock_id": ticker})
    out = pd.DataFrame(rows)
    if out.duplicated(["signal_date", "stock_id"]).any():
        raise SystemExit("FAIL: matched placebo contains duplicate logical keys")
    expected = baseline.groupby("signal_date").size()
    actual = out.groupby("signal_date").size()
    if not expected.equals(actual):
        raise SystemExit("FAIL: matched placebo does not preserve per-date signal counts")
    return out.sort_values(["signal_date", "stock_id"]).reset_index(drop=True)


def _run(
    *,
    name: str,
    signals: pd.DataFrame,
    sim_sessions: list[pd.Timestamp],
    ca_instructions,
    ticker_scope: set[str],
) -> dict[str, object]:
    portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(
            SourceDataAdapter(SOURCE_ROOT),
            ticker_scope=ticker_scope,
        ),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.10,
            max_positions=10,
            stop_fraction=0.12,
            reentry_gap_sessions=20,
            max_hold_sessions=250,
            lot_size=1000,
            random_seed=0,
        )
    )
    simulator = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=SignalDeclaration(
            source=f"MATCHED_PLACEBO:{name}",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=2),
    )
    result = simulator.run(
        sessions=[x.date() for x in sim_sessions],
        signals=signals,
        corporate_actions=ca_instructions,
    )
    dates = pd.DatetimeIndex([pd.Timestamp(x.session_date) for x in result.sessions])
    nav = pd.Series(
        [float(x.snapshot.valuation.nav) for x in result.sessions],
        index=dates,
        dtype=float,
    )
    if nav.empty or (nav <= 0).any():
        raise SystemExit(f"FAIL {name}: invalid NAV")
    return {
        "scenario": name,
        "signals": len(signals),
        "entries": result.total_entries,
        "stop_exits": result.total_stop_exits,
        "max_hold_exits": result.total_max_hold_exits,
        "blocked_exits": result.total_blocked_exits,
        **_metrics(nav),
    }


def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)

    baseline = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    baseline = baseline[
        baseline["signal_date"].between(SIGNAL_START, SIGNAL_END)
    ].copy()

    quarantined = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)
    excluded = set(quarantined) | COMMON_SUPPORT_EXCLUDED_TICKERS
    baseline = baseline[
        ~baseline["stock_id"].astype(str).isin(excluded)
    ][["signal_date", "stock_id"]].copy()
    baseline = baseline.sort_values(["signal_date", "stock_id"]).reset_index(drop=True)

    eligible = _eligible_turnover_universe(adjusted, tradability, excluded)
    placebos = {
        seed: _matched_random_signals(
            baseline=baseline,
            eligible=eligible,
            seed=seed,
        )
        for seed in SEEDS
    }

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    end_pos = max(i for i, x in enumerate(market_sessions) if x <= SIGNAL_END)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]

    ticker_scope = set(baseline["stock_id"].astype(str))
    for p in placebos.values():
        ticker_scope.update(p["stock_id"].astype(str))

    ca_instructions, unsupported_count, unsupported_summary = build_supported_ca(
        candidate_tickers=ticker_scope,
        sessions=set(sim_sessions),
    )
    if unsupported_count:
        raise SystemExit(f"BLOCKED: unsupported CA rows {unsupported_summary}")

    rows = [
        _run(
            name="baseline_common_support",
            signals=baseline,
            sim_sessions=sim_sessions,
            ca_instructions=ca_instructions,
            ticker_scope=ticker_scope,
        )
    ]
    for seed in SEEDS:
        rows.append(
            _run(
                name=f"matched_random_seed{seed}",
                signals=placebos[seed],
                sim_sessions=sim_sessions,
                ca_instructions=ca_instructions,
                ticker_scope=ticker_scope,
            )
        )

    frame = pd.DataFrame(rows)
    baseline_row = frame.iloc[0]
    frame["cagr_delta_pp_vs_baseline"] = (
        frame["cagr"] - baseline_row["cagr"]
    ) * 100.0
    frame["final_nav_vs_baseline"] = (
        frame["final_nav"] / baseline_row["final_nav"] - 1.0
    )

    placebo_rows = frame.iloc[1:]
    checks = {
        "all_prespecified_runs_complete": len(frame) == 4,
        "per_date_signal_counts_matched": all(
            baseline.groupby("signal_date").size().equals(
                p.groupby("signal_date").size()
            )
            for p in placebos.values()
        ),
        "common_support_exclusion_active": not bool(ticker_scope & excluded),
        "all_nav_positive": bool(frame["final_nav"].gt(0).all()),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Date-Count-Matched Random-Control Diagnostic",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: test whether the breakout stock selection adds information beyond simply owning same-day names from the same top-25%-turnover eligible universe. Each random control preserves the exact number of signal candidates on every signal date.",
        "",
        "## Design",
        "",
        "- baseline: canonical 250-session breakout candidates on common support.",
        "- controls: same-date random non-breakout names from the same eligible top-25%-turnover universe.",
        "- random seeds fixed before this run: 101, 202, 303.",
        "- each control preserves baseline candidate count on every signal date.",
        "- accounting, RAW execution, portfolio policy, CA handling, PIT exclusions, board lot, and zero-friction assumptions are unchanged.",
        "",
        "## Results",
        "",
        "| Scenario | Signals | Entries | Stop exits | Max-hold exits | Blocked exits | Final NAV | CAGR | Max DD | Sharpe | Final NAV vs baseline | CAGR delta pp |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.signals:,} | {row.entries:,} | {row.stop_exits:,} "
            f"| {row.max_hold_exits:,} | {row.blocked_exits:,} | {row.final_nav:,.2f} "
            f"| {row.cagr*100:.2f}% | {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} "
            f"| {row.final_nav_vs_baseline*100:.2f}% | {row.cagr_delta_pp_vs_baseline:.2f} |"
        )

    lines += [
        "",
        "## Control summary",
        "",
        f"- random-control CAGR range: {placebo_rows['cagr'].min()*100:.2f}% to {placebo_rows['cagr'].max()*100:.2f}%",
        f"- baseline CAGR: {baseline_row['cagr']*100:.2f}%",
        f"- random controls above baseline CAGR: {int(placebo_rows['cagr'].gt(baseline_row['cagr']).sum())} / {len(placebo_rows)}",
        "",
        "## Operational gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "## Interpretation boundary",
        "",
        "This is a diagnostic, not a promotion rule. If matched random controls perform similarly to or better than the breakout baseline, that is adverse evidence for breakout-specific information under the present portfolio policy. No control result is used to select or retune the strategy.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if status != "PASS":
        raise SystemExit("FAIL: matched-placebo operational gate failed")


if __name__ == "__main__":
    main()
