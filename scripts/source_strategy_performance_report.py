#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
from astraquant.research.config_io import load_run_config
from astraquant.research.contact_registry import ContactRecord, append_contact_record
from astraquant.research.epoch_governance import (
    Epoch,
    EpochGovernanceError,
    load_strategy_version_registry,
    resolve_effect_period,
)
from astraquant.research.signal_engine import SignalContext
from astraquant.research.universe_engine import UniverseContext

from source_config_sweep import (
    EXPECTED_EXCLUSIONS_SHA256,
    _load_exclusions,
    _research_panel,
)
from source_strategy_integration_smoke import build_supported_ca, pit_unsafe_ca_tickers

RUN_CONFIG = os.environ.get("RUN_CONFIG", "").strip()
REQUESTED_EPOCH = os.environ.get("RESEARCH_EPOCH", "E1").strip().upper()
STRATEGY_VERSION_REGISTRY = Path(
    os.environ.get("STRATEGY_VERSION_REGISTRY", "data/research/strategy_versions.csv")
)
CONTACT_REGISTRY_PATH = Path(
    os.environ.get("CONTACT_REGISTRY_PATH", "docs/CONTACT_REGISTRY.md")
)
LEGACY_REPORT_PATH = "docs/SOURCE_STRATEGY_PERFORMANCE_REPORT.md"
SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
SOURCE_REVISION = os.environ.get("SOURCE_REVISION", "source-checkout")
INITIAL_CASH = 10_000_000.0


def _default_report_path() -> str:
    if not RUN_CONFIG:
        return LEGACY_REPORT_PATH
    return f"docs/SOURCE_{Path(RUN_CONFIG).stem.upper()}_STRATEGY_PERFORMANCE.md"


REPORT_PATH = Path(os.environ.get("REPORT_PATH", "").strip() or _default_report_path())
TRADE_CSV_PATH = Path(
    os.environ.get("TRADE_CSV_PATH", "").strip()
    or str(REPORT_PATH.with_suffix("")) + "_TRADES.csv"
)
OPEN_LOTS_CSV_PATH = Path(
    os.environ.get("OPEN_LOTS_CSV_PATH", "").strip()
    or str(REPORT_PATH.with_suffix("")) + "_OPEN_LOTS.csv"
)


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


def _strategy_version() -> str:
    if not RUN_CONFIG:
        return "legacy_breakout_v1"
    return load_run_config(RUN_CONFIG).strategy_version


def _effect_period():
    registry = load_strategy_version_registry(STRATEGY_VERSION_REGISTRY)
    version = _strategy_version()
    if version not in registry:
        raise SystemExit(f"BLOCKED: strategy_version not registered: {version}")
    try:
        period = resolve_effect_period(registry[version], REQUESTED_EPOCH)
    except EpochGovernanceError as exc:
        raise SystemExit(f"BLOCKED: {exc}") from exc
    if period.epoch is Epoch.E4:
        raise SystemExit(
            "BLOCKED: E4 protocol is registered but this historical report runner does not execute forward validation"
        )
    assert period.end is not None
    return version, period


STRATEGY_VERSION, EFFECT_PERIOD = _effect_period()
SIGNAL_START = pd.Timestamp(EFFECT_PERIOD.start)
SIGNAL_END = pd.Timestamp(EFFECT_PERIOD.end)


def _legacy_breakout_candidates(
    *, adjusted: pd.DataFrame, tradability: pd.DataFrame
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
    signals = signals[~signals["stock_id"].astype(str).isin(quarantined_tickers)].copy()
    declaration = SignalDeclaration(
        source="CANONICAL_SIMPLE_BREAKOUT_V1",
        price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
    )
    candidates = legacy_signals_to_candidates(signals, declaration=declaration)
    return (
        candidates,
        _base_policy(),
        declaration.source,
        quarantined_signal_rows,
        quarantined_tickers,
    )


def _config_candidates(
    *, panel: pd.DataFrame
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
    if prepared.run_config.strategy_version != STRATEGY_VERSION:
        raise SystemExit("BLOCKED: run config strategy_version changed during preparation")
    candidates = prepared.candidates[
        prepared.candidates["signal_date"].between(
            SIGNAL_START, SIGNAL_END, inclusive="both"
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


def _write_trade_tables(trade_report, *, period_end: pd.Timestamp) -> None:
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
                "held_days_at_period_end": (period_end.date() - x.opened_at.date()).days,
                "unit_cost": x.unit_cost,
            }
            for x in trade_report.reconstruction.open_lots
        ]
    )
    open_lots.to_csv(OPEN_LOTS_CSV_PATH, index=False)


def _open_lot_disclosure(trade_report, *, period_end: pd.Timestamp) -> list[str]:
    open_lots = tuple(trade_report.reconstruction.open_lots)
    open_sources = {x.source_fill_id for x in open_lots}
    closed_sources = {x.source_fill_id for x in trade_report.closed_trades}
    all_sources = open_sources | closed_sources
    share = len(open_sources) / len(all_sources) if all_sources else float("nan")
    share_text = "n/a" if pd.isna(share) else f"{share * 100:.2f}%"
    lines = [
        "",
        "## 期末未平倉揭露",
        "",
        f"- 未平倉 entry sources: {len(open_sources):,}",
        f"- 未平倉佔全部已觀察 entry sources: {share_text}",
        "- 未平倉部位不強制平倉，且未讀取下一時期價格補完。",
        "",
        "| Source fill | Current ticker | Entry date | Held days at period end |",
        "|---|---|---|---:|",
    ]
    for lot in open_lots:
        held = (period_end.date() - lot.opened_at.date()).days
        lines.append(
            f"| {lot.source_fill_id} | {lot.ticker} | {lot.opened_at.date()} | {held} |"
        )
    if not open_lots:
        lines.append("| — | — | — | 0 |")
    return lines


def _record_contact() -> None:
    append_contact_record(
        CONTACT_REGISTRY_PATH,
        ContactRecord(
            result_id=REPORT_PATH.stem,
            covered_period=f"{SIGNAL_START.date()} ~ {SIGNAL_END.date()}",
            contact_date=datetime.now(ZoneInfo("Asia/Taipei")).date(),
            context=(
                f"strategy effect report; strategy_version={STRATEGY_VERSION}; "
                f"epoch={EFFECT_PERIOD.epoch.value}; source_revision={SOURCE_REVISION}"
            ),
        ),
    )


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
        ) = _legacy_breakout_candidates(adjusted=adjusted, tradability=tradability)
        report_mode = "legacy-breakout"
    else:
        (
            candidates,
            policy_config,
            signal_source,
            quarantined_signal_rows,
            quarantined_tickers,
        ) = _config_candidates(panel=panel)
        report_mode = f"config:{RUN_CONFIG}"

    sim_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if SIGNAL_START <= pd.Timestamp(x) <= SIGNAL_END
    ]
    if not sim_sessions:
        raise SystemExit("BLOCKED: no source sessions inside governed epoch")
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
            SourceDataAdapter(SOURCE_ROOT), ticker_scope=valuation_tickers
        ),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(), slippage_model=FixedBpsSlippage(bps=0)
        ),
        portfolio=portfolio,
    )
    simulator = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=PortfolioIntentPolicy(policy_config),
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
    _write_trade_tables(trade_report, period_end=dates[-1])
    fills = portfolio_fills(portfolio)
    total_return_index = load_finmind_total_return_index(
        SOURCE_ROOT / "futures" / "index_tri.parquet", stock_id="TAIEX"
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
        "governed_epoch_start": dates[0] >= SIGNAL_START,
        "governed_epoch_end": dates[-1] <= SIGNAL_END,
        "no_next_epoch_drain": dates[-1] <= SIGNAL_END,
        "raw_nav_series_complete": len(nav) == len(sim_sessions),
        "no_unsupported_ca_cash": unsupported_ca_cash == 0,
        "pit_unsafe_ca_tickers_excluded": not bool(candidate_signal_tickers & quarantined_tickers),
        "candidate_signal_ids_four_digit_only": bool(
            candidates["stock_id"].astype(str).str.fullmatch(r"[1-9]\d{3}", na=False).all()
        ),
        "positive_nav_all_sessions": bool((nav > 0).all()),
        "benchmark_same_trading_days": comparison.benchmark_nav.index.equals(nav.index),
        "fifo_trade_table_written": TRADE_CSV_PATH.exists(),
        "open_lots_table_written": OPEN_LOTS_CSV_PATH.exists(),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    lines = [
        "# Canonical Config Strategy Performance + Total-Return Benchmark Report",
        "",
        f"Status: **{status}**",
        "",
        f"Epoch: **{EFFECT_PERIOD.label}**",
        "",
        "This report is governed historical evidence. It is not parameter promotion, OOS unlock, or an investment recommendation.",
        "",
        "## Run identity",
        "",
        f"- strategy_version: {STRATEGY_VERSION}",
        f"- mode: {report_mode}",
        f"- signal source: {signal_source}",
        f"- signal/effect window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- simulation horizon: {dates[0].date()} through {dates[-1].date()}",
        "- next-epoch drain: prohibited",
        f"- RAW strategy NAV sessions: {len(nav):,}",
        f"- starting capital: {INITIAL_CASH:,.2f}",
        f"- canonical candidates supplied: {len(candidates):,}",
        f"- PIT-unsafe CA tickers quarantined: {len(quarantined_tickers):,}",
        f"- legacy signal rows removed by PIT CA quarantine: {quarantined_signal_rows:,}",
        "- strategy execution assumptions: zero explicit fees and zero slippage in this descriptive run",
        "- benchmark: FinMind TaiwanStockTotalReturnIndex (TAIEX), same starting capital and exact strategy trading dates",
        f"- closed FIFO trade table: `{TRADE_CSV_PATH.as_posix()}`",
        f"- open FIFO lots table: `{OPEN_LOTS_CSV_PATH.as_posix()}`",
        "",
    ]
    lines += render_benchmark_report_sections(
        trade_report=trade_report, comparison=comparison
    )
    lines += _open_lot_disclosure(trade_report, period_end=dates[-1])
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
        "Closed-trade statistics and period-end open-lot disclosure are reported separately; open lots are not forced closed.",
        "CAGR / MaxDD / Sharpe are secondary portfolio-path context; the trade-level table is primary.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _record_contact()
    if status != "PASS":
        raise SystemExit("FAIL: performance/benchmark reproducibility gate failed")


if __name__ == "__main__":
    main()
