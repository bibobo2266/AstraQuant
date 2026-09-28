#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.features.technical import BreakoutSignalConfig, build_simple_breakout_signals
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.policy import CapacitySelectionRule, PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationConfig

from source_strategy_integration_smoke import (
    DRAIN_SESSIONS,
    SIGNAL_END,
    SIGNAL_START,
    build_supported_ca,
    load_adjusted,
    load_tradability,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_POLICY_CAPACITY_ATTRIBUTION.md"))
EXCLUSIONS_PATH = Path(os.environ.get("EXCLUSIONS_PATH", "docs/SOURCE_CA_PIT_EXCLUSIONS.csv"))
EXPECTED_EXCLUSIONS_SHA256 = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
INITIAL_CASH = 10_000_000.0

RULES = (
    ("ticker_asc", CapacitySelectionRule.TICKER_ASC),
    ("turnover_desc", CapacitySelectionRule.TURNOVER_DESC),
    ("turnover_asc", CapacitySelectionRule.TURNOVER_ASC),
    ("breakout_excess_desc", CapacitySelectionRule.BREAKOUT_EXCESS_DESC),
    ("hash_asc", CapacitySelectionRule.HASH_ASC),
)


def _metrics(nav: pd.Series) -> dict[str, float]:
    daily = nav.pct_change().dropna()
    elapsed_years = (nav.index[-1] - nav.index[0]).days / 365.2425
    cagr = (nav.iloc[-1] / INITIAL_CASH) ** (1.0 / elapsed_years) - 1.0
    dd = nav / nav.cummax() - 1.0
    sharpe = (
        float(daily.mean() / daily.std(ddof=1) * math.sqrt(252))
        if len(daily) > 1 and daily.std(ddof=1) > 0
        else float("nan")
    )
    return {
        "final_nav": float(nav.iloc[-1]),
        "cagr": float(cagr),
        "max_drawdown": float(dd.min()),
        "sharpe": sharpe,
    }


def _load_frozen_exclusions() -> set[str]:
    digest = hashlib.sha256(EXCLUSIONS_PATH.read_bytes()).hexdigest()
    if digest != EXPECTED_EXCLUSIONS_SHA256:
        raise SystemExit(
            "BLOCKED: frozen P2-060 exclusion ledger hash changed "
            f"(expected {EXPECTED_EXCLUSIONS_SHA256}, got {digest})"
        )
    frame = pd.read_csv(EXCLUSIONS_PATH, dtype={"ticker": str})
    required = {"ticker", "effective_date", "event_type", "policy_reason", "source"}
    if not required.issubset(frame.columns):
        raise SystemExit("BLOCKED: frozen exclusion ledger schema changed")
    return set(frame["ticker"].astype(str))


def _run_rule(*, name, rule, signals, sim_sessions, ca_instructions, ticker_scope):
    portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(SourceDataAdapter(SOURCE_ROOT), ticker_scope=ticker_scope),
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
            capacity_selection_rule=rule,
        )
    )
    simulator = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=SignalDeclaration(
            source=f"POLICY_CAPACITY_ATTRIBUTION:{name}",
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
        "rule": name,
        "entries": result.total_entries,
        "stop_exits": result.total_stop_exits,
        "max_hold_exits": result.total_max_hold_exits,
        "blocked_exits": result.total_blocked_exits,
        "capacity_overflow_sessions": result.total_capacity_overflow_sessions,
        "capacity_only_rejections": result.total_capacity_rejections,
        **_metrics(nav),
    }


def main() -> None:
    excluded = _load_frozen_exclusions()
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)
    signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = signals[
        signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
        & ~signals["stock_id"].astype(str).isin(excluded)
    ].copy()
    if signals.empty:
        raise SystemExit("BLOCKED: no breakout signals remain on frozen common support")
    if signals[["breakout_excess", "turnover_value"]].isna().any().any():
        raise SystemExit("BLOCKED: deterministic ranking metadata contains nulls")

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    end_pos = max(i for i, x in enumerate(market_sessions) if x <= SIGNAL_END)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]

    ticker_scope = set(signals["stock_id"].astype(str))
    if ticker_scope & excluded:
        raise SystemExit("FAIL: frozen common-support exclusion leaked into signal scope")

    ca_instructions, unsupported_count, unsupported_summary = build_supported_ca(
        candidate_tickers=set(ticker_scope),
        sessions=set(sim_sessions),
    )
    if unsupported_count:
        raise SystemExit(
            "BLOCKED: new CA blocker after frozen common-support application "
            f"{unsupported_summary}"
        )

    frame = pd.DataFrame([
        _run_rule(
            name=name,
            rule=rule,
            signals=signals,
            sim_sessions=sim_sessions,
            ca_instructions=ca_instructions,
            ticker_scope=ticker_scope,
        )
        for name, rule in RULES
    ])

    breakout_row = frame[frame["rule"].eq("breakout_excess_desc")].iloc[0]
    neutral = frame[frame["rule"].isin(["ticker_asc", "hash_asc"])]

    checks = {
        "frozen_exclusion_hash_matches": True,
        "all_five_prespecified_rules_complete": len(frame) == len(RULES),
        "common_support_exclusion_active": not bool(ticker_scope & excluded),
        "ranking_metadata_complete": not bool(signals[["turnover_value", "breakout_excess"]].isna().any().any()),
        "all_nav_positive": bool(frame["final_nav"].gt(0).all()),
        "no_new_ca_blocker": unsupported_count == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Policy / Capacity Attribution Diagnostic",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: separate breakout signal information from portfolio capacity-selection mechanics under the frozen P2-060 common-support universe. Rule order was fixed before observing these results; no rule is selected or promoted.",
        "",
        "## Frozen configuration",
        "",
        "- lookback: 250 sessions",
        "- turnover universe: top 25% by same-day turnover",
        "- RAW execution/accounting and normalized CA/PIT/terminal/successor handling unchanged",
        "- target position size: 10% NAV",
        "- maximum positions: 10",
        "- stop: 12%",
        "- re-entry gap: 20 sessions",
        "- maximum hold: 250 sessions",
        "- board lot: 1000 shares",
        "- explicit fee/slippage: zero for signal-isolation",
        f"- frozen P2-060 exclusion ledger SHA-256: {EXPECTED_EXCLUSIONS_SHA256}",
        f"- frozen excluded tickers: {len(excluded):,}",
        f"- retained common-support signal tickers: {len(ticker_scope):,}",
        "",
        "## Prespecified deterministic rule order",
        "",
        "1. ticker ascending",
        "2. highest turnover",
        "3. lowest turnover",
        "4. strongest causal breakout excess",
        "5. deterministic SHA-256(date|ticker) neutral control",
        "",
        "Breakout excess is computed on the signal session as adjusted_close / prior_250_session_high - 1. The prior high uses only observations strictly before the signal session, and entries remain next-session RAW open.",
        "",
        "## Results",
        "",
        "| Rule | Final NAV | CAGR | Max DD | Sharpe | Entries | Stop exits | Max-hold exits | Blocked exits | Capacity overflow sessions | Capacity-only rejects |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.rule} | {row.final_nav:,.2f} | {row.cagr*100:.2f}% "
            f"| {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} | {row.entries:,} "
            f"| {row.stop_exits:,} | {row.max_hold_exits:,} | {row.blocked_exits:,} "
            f"| {row.capacity_overflow_sessions:,} | {row.capacity_only_rejections:,} |"
        )

    lines += [
        "",
        "## Deterministic-rule dispersion",
        "",
        f"- CAGR range: {frame['cagr'].min()*100:.2f}% to {frame['cagr'].max()*100:.2f}%",
        f"- CAGR spread: {(frame['cagr'].max()-frame['cagr'].min())*100:.2f} percentage points",
        f"- final NAV range: {frame['final_nav'].min():,.2f} to {frame['final_nav'].max():,.2f}",
        f"- breakout-excess-priority CAGR: {breakout_row['cagr']*100:.2f}%",
        f"- neutral deterministic CAGR range (ticker/hash): {neutral['cagr'].min()*100:.2f}% to {neutral['cagr'].max()*100:.2f}%",
        "",
        "## Historical context, not directly comparable",
        "",
        "- P2-056 pre-P2-060 matched-random controls had CAGR 14.84% to 21.07%, with baseline 19.20%.",
        "- P2-057 pre-P2-060 capacity-seed sensitivity had CAGR 15.15% to 19.79%, a 4.64 percentage-point spread.",
        "- Those runs used an earlier common-support scope. They remain historical adverse/path-dependence evidence but are not direct numeric comparators for this P2-060-frozen attribution.",
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
        "This diagnostic does not choose a rule, tune a parameter, promote a strategy, or unlock locked OOS. The question is whether breakout-strength priority separates materially from neutral deterministic capacity rules once random slot selection is removed.",
        "",
        "External validity is limited to the P2-060 common-support sub-universe. The frozen policy excludes 355 of 1,986 eligible-universe tickers (17.9%), concentrated in securities with capital reductions or par-value/share-coordinate changes plus four late-known dividend events. Results must not be generalized automatically to the full Taiwan top-25%-turnover universe.",
        "",
        "Turnover/churn is not separately reported because the canonical simulator does not yet expose gross traded notional; entries and exit counts are reported without inventing a turnover proxy.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    if status != "PASS":
        raise SystemExit("FAIL: policy/capacity attribution operational gate failed")


if __name__ == "__main__":
    main()
