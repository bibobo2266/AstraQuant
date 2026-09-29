#!/usr/bin/env python3
from __future__ import annotations

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
from astraquant.portfolio.performance_reporting import build_trade_report, portfolio_fills
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationConfig
from astraquant.research.benchmark import (
    compare_strategy_to_total_return_benchmark,
    load_finmind_total_return_index,
    render_benchmark_report_sections,
)
from astraquant.research.candidates import legacy_signals_to_candidates
from astraquant.research.config_engine import ResearchConfigEngine
from astraquant.research.signal_engine import SignalContext
from astraquant.research.universe_engine import UniverseContext

from source_config_sweep import (
    EXPECTED_EXCLUSIONS_SHA256,
    _load_exclusions,
    _research_panel,
)
from source_strategy_integration_smoke import (
    SIGNAL_START,
    SIGNAL_END,
    DRAIN_SESSIONS,
    build_supported_ca,
    pit_unsafe_ca_tickers,
)

REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_STRATEGY_PERFORMANCE_REPORT.md"))
TRADE_CSV_PATH = Path(
    os.environ.get(
        "TRADE_CSV_PATH",
        str(REPORT_PATH.with_suffix("")) + "_TRADES.csv",
    )
)
OPEN_LOTS_CSV_PATH = Path(
    os.environ.get(
        "OPEN_LOTS_CSV_PATH",
        str(REPORT_PATH.with_suffix("")) + "_OPEN_LOTS.csv",
    )
)
RUN_CONFIG = os.environ.get("RUN_CONFIG", "").strip()
SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
SOURCE_REVISION = os.environ.get("SOURCE_REVISION", "source-checkout")
INITIAL_CASH = 10_000_000.0
EXPECTED_LONG_NAV = 51_696_620.29773994


def _base_policy() -> PortfolioPolicyConfig:
    return PortfolioPolicyConfig(
        position_fraction=0.10,
        max_positions=10,
        stop_fraction=0.12,
        reentry_gap_sessions=20,
        max_hold_sessions=250,
        lot_size=1000,
        random_seed=0,
    )


def _legacy_breakout_candidates(
    *,
    adjusted: pd.DataFrame,
    tradability: pd.DataFrame,
) -> tuple[pd.DataFrame, PortfolioPolicyConfig, str, int, set[str]]:
    all_signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = all_signals[
        all_signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
    ].copy()

    quarantined_tickers = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)
    quarantined_signal_rows = int(
        signals["stock_id"].astype(str).isin(quarantined_tickers).sum()
    )
    signals = signals[
        ~signals["stock_id"].astype(str).isin(quarantined_tickers)
    ].copy()
    declaration = SignalDeclaration(
        source="CANONICAL_SIMPLE_BREAKOUT_V1",
        price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
    )
    candidates = legacy_signals_to_candidates(
        signals,
        declaration=declaration,
    )
    return (
        candidates,
        _base_policy(),
        declaration.source,
        quarantined_signal_rows,
        quarantined_tickers,
    )


def _config_candidates(
    *,
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, PortfolioPolicyConfig, str, int, set[str]]:
    if not RUN_CONFIG:
        raise ValueError("RUN_CONFIG is required for config mode")
    excluded = _load_exclusions()
    engine = ResearchConfigEngine()
    prepared = engine.prepare(
        run_config_path=RUN_CONFIG,
        root=Path("."),
        panel=panel,
        universe_context=UniverseContext(
            p2_060_excluded_tickers=frozenset(excluded),
            p2_060_exclusion_sha256=EXPECTED_EXCLUSIONS_SHA256,
            theme_root=Path("themes") if Path("themes").exists() else None,
        ),
        signal_context=SignalContext(source_revision=SOURCE_REVISION),
        base_policy=_base_policy(),
    )
    candidates = prepared.candidates[
        prepared.candidates["signal_date"].between(
            SIGNAL_START,
            SIGNAL_END,
            inclusive="both",
        )
    ].copy()
    if not candidates["stock_id"].astype(str).str.fullmatch(r"[1-9]\d{3}", na=False).all():
        raise SystemExit("FAIL: config candidate universe contains non-four-digit signal IDs")

    quarantined_tickers = pit_unsafe_ca_tickers(start=SIGNAL_START, end=SIGNAL_END)
    leaked = set(candidates["stock_id"].astype(str)) & quarantined_tickers
    if leaked:
        raise SystemExit(
            "FAIL: config candidates include PIT-unsafe CA tickers: "
            + ",".join(sorted(leaked))
        )
    return (
        candidates,
        prepared.portfolio_policy,
        f"CONFIG:{prepared.signal_config.name}",
        0,
        quarantined_tickers,
    )


def _write_trade_tables(trade_report) -> None:
    TRADE_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    closed = pd.DataFrame(
        [
            {
                "source_fill_id": x.source_fill_id,
                "entry_ticker": x.entry_ticker,
                "entry_at": x.entry_at,
                "exit_at": x.exit_at,
                "realized_pnl": x.realized_pnl,
                "entry_cost": x.entry_cost,
                "return_on_cost": x.return_on_cost,
                "holding_days": x.holding_days,
                "exit_components": ";".join(x.exit_components),
            }
            for x in trade_report.closed_trades
        ]
    )
    closed.to_csv(TRADE_CSV_PATH, index=False)

    open_lots = pd.DataFrame(
        [
            {
                "source_fill_id": x.source_fill_id,
                "current_ticker": x.ticker,
                "quantity": x.quantity,
                "opened_at": x.opened_at,
                "unit_cost": x.unit_cost,
            }
            for x in trade_report.reconstruction.open_lots
        ]
    )
    open_lots.to_csv(OPEN_LOTS_CSV_PATH, index=False)


def main() -> None:
    panel, adjusted, tradability = _research_panel()
    legacy_mode = not bool(RUN_CONFIG)

    if legacy_mode:
        (
            candidates,
            policy_config,
            signal_source,
            quarantined_signal_rows,
            quarantined_tickers,
        ) = _legacy_breakout_candidates(
            adjusted=adjusted,
            tradability=tradability,
        )
        report_mode = "legacy-breakout-regression"
    else:
        (
            candidates,
            policy_config,
            signal_source,
            quarantined_signal_rows,
            quarantined_tickers,
        ) = _config_candidates(panel=panel)
        report_mode = f"config:{RUN_CONFIG}"

    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    eligible_end_positions = [i for i, x in enumerate(market_sessions) if x <= SIGNAL_END]
    if not eligible_end_positions:
        raise SystemExit("BLOCKED: signal end precedes first source session")
    end_pos = max(eligible_end_positions)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]
    session_set = set(sim_sessions)

    valuation_tickers = set(candidates["stock_id"].astype(str))
    ca_instructions, unsupported_ca_cash, unsupported_ca_summary = build_supported_ca(
        candidate_tickers=valuation_tickers,
        sessions=session_set,
    )
    if unsupported_ca_cash:
        raise SystemExit(
            "BLOCKED: unsupported corporate-action rows remain "
            f"{unsupported_ca_summary}"
        )

    portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(
            SourceDataAdapter(SOURCE_ROOT),
            ticker_scope=valuation_tickers,
        ),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    policy = PortfolioIntentPolicy(policy_config)
    simulator = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=SignalDeclaration(
            source=signal_source,
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=2),
    )

    result = simulator.run(
        sessions=[x.date() for x in sim_sessions],
        candidates=candidates,
        corporate_actions=ca_instructions,
    )

    dates = pd.DatetimeIndex([pd.Timestamp(x.session_date) for x in result.sessions])
    nav = pd.Series(
        [float(x.snapshot.valuation.nav) for x in result.sessions],
        index=dates,
        dtype=float,
    )
    if nav.empty or (nav <= 0).any():
        raise SystemExit("FAIL: NAV series is empty or nonpositive")

    trade_report = build_trade_report(portfolio)
    _write_trade_tables(trade_report)
    fills = portfolio_fills(portfolio)
    total_return_index = load_finmind_total_return_index(
        SOURCE_ROOT / "futures" / "index_tri.parquet",
        stock_id="TAIEX",
    )
    comparison = compare_strategy_to_total_return_benchmark(
        strategy_nav=nav,
        total_return_index=total_return_index,
        initial_cash=INITIAL_CASH,
        fills=fills,
        trade_report=trade_report,
    )

    candidate_signal_tickers = set(candidates["stock_id"].astype(str))
    checks = {
        "same_signal_window_as_long_horizon_probe": (
            SIGNAL_START == pd.Timestamp("2016-01-04")
            and SIGNAL_END == pd.Timestamp("2026-06-30")
        ),
        "simulation_ends_on_2026_07_07": dates[-1] == pd.Timestamp("2026-07-07"),
        "raw_nav_series_complete": len(nav) == len(sim_sessions),
        "no_unsupported_ca_cash": unsupported_ca_cash == 0,
        "pit_unsafe_ca_tickers_excluded": not bool(
            candidate_signal_tickers & quarantined_tickers
        ),
        "candidate_signal_ids_four_digit_only": bool(
            candidates["stock_id"].astype(str).str.fullmatch(r"[1-9]\d{3}", na=False).all()
        ),
        "positive_nav_all_sessions": bool((nav > 0).all()),
        "benchmark_same_trading_days": comparison.benchmark_nav.index.equals(nav.index),
        "fifo_trade_table_written": TRADE_CSV_PATH.exists(),
        "open_lots_table_written": OPEN_LOTS_CSV_PATH.exists(),
    }
    if legacy_mode:
        checks["frozen_long_nav_exact_float_check"] = (
            float(nav.iloc[-1]) == EXPECTED_LONG_NAV
        )

    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Canonical Config Strategy Performance + Total-Return Benchmark Report",
        "",
        f"Status: **{status}**",
        "",
        "This is descriptive in-sample evidence. It is not OOS validation, parameter promotion, or an investment recommendation.",
        "",
        "## Run identity",
        "",
        f"- mode: {report_mode}",
        f"- signal source: {signal_source}",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- simulation/drain horizon: {dates[0].date()} through {dates[-1].date()}",
        f"- RAW strategy NAV sessions: {len(nav):,}",
        f"- starting capital: {INITIAL_CASH:,.2f}",
        f"- canonical candidates supplied: {len(candidates):,}",
        f"- PIT-unsafe CA tickers quarantined: {len(quarantined_tickers):,}",
        f"- legacy signal rows removed by PIT CA quarantine: {quarantined_signal_rows:,}",
        "- executable exit layer in this round remains limited to fixed stop + time/max-hold only",
        "- execution/accounting and verified CA semantics remain unchanged; this round adds the documented conservative unverified-terminal cashout overlay",
        "- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run",
        "- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), buy-and-hold, same starting capital and exact strategy trading dates, no benchmark transaction-cost deduction",
        f"- closed FIFO trade table: `{TRADE_CSV_PATH.as_posix()}`",
        f"- open FIFO lots table: `{OPEN_LOTS_CSV_PATH.as_posix()}`",
        "",
    ]
    lines += render_benchmark_report_sections(
        trade_report=trade_report,
        comparison=comparison,
    )
    lines += [
        "",
        "## Accounting/activity audit",
        "",
        f"- final strategy NAV: {nav.iloc[-1]:,.2f}",
        f"- entries executed: {result.total_entries:,}",
        f"- RAW stop exits: {result.total_stop_exits:,}",
        f"- RAW max-hold exits: {result.total_max_hold_exits:,}",
        f"- blocked exit attempts: {result.total_blocked_exits:,}",
        f"- corporate actions applied: {result.total_corporate_actions:,}",
        f"- corporate-action cash payments settled: {result.total_corporate_cash_payments:,}",
        f"- ending pending receivables: {portfolio.cash.pending_receivables:,.6f}",
        f"- ending pending payables: {portfolio.cash.pending_payables:,.6f}",
        "",
        "## Reproducibility gates",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for name, ok in checks.items():
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} |")

    lines += [
        "",
        "Closed-trade statistics come from CA-aware FIFO reconstruction. Any entry with a remaining open FIFO lot is excluded from closed-trade statistics and reported separately.",
        "CAGR / MaxDD / Sharpe are secondary portfolio-path context; the trade-level table is primary.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if status != "PASS":
        raise SystemExit("FAIL: performance/benchmark reproducibility gate failed")


if __name__ == "__main__":
    main()
