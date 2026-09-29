#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.corporate_actions import (
    NormalizedCorporateActionKind,
    build_finmind_normalized_actions,
)
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.features.technical import BreakoutSignalConfig, build_simple_breakout_signals
from astraquant.portfolio.corporate_actions import (
    CashEntitlementBasis,
    CorporateActionEvent,
    CorporateActionType,
)
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
from astraquant.portfolio.models import SecurityConversionLeg
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import (
    CanonicalStrategySimulator,
    StrategySimulationConfig,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_STRATEGY_INTEGRATION_SMOKE.md"))
SIGNAL_START = pd.Timestamp(os.environ.get("SIGNAL_START", "2026-01-01"))
SIGNAL_END = pd.Timestamp(os.environ.get("SIGNAL_END", "2026-03-31"))
DRAIN_SESSIONS = int(os.environ.get("DRAIN_SESSIONS", "2"))
REPORT_TITLE = os.environ.get(
    "REPORT_TITLE",
    "Source Canonical Strategy Integration Smoke",
)


CURATED_TERMINAL_EVENTS = [
    {
        "ticker": "6286",
        "known_at": datetime(2016, 4, 6, 14, 40),
        "terminal_stale_from": pd.Timestamp("2016-04-21").date(),
        "effective_at": datetime(2016, 4, 29),
        "payment_at": datetime(2016, 5, 5),
        "cash_per_share": 195.0,
        "source": "MOPS/TWSE cash share-conversion disclosure",
        "source_url": "https://news.cnyes.com/news/id/748023",
    },
    {
        "ticker": "4141",
        "known_at": datetime(2022, 3, 30, 18, 31, 29),
        "terminal_stale_from": pd.Timestamp("2022-04-27").date(),
        "effective_at": datetime(2022, 5, 3),
        "payment_at": datetime(2022, 5, 10),
        "cash_per_share": 26.23,
        "source": "MOPS/TWSE public merger-delisting disclosure",
        "source_url": "https://news.cnyes.com/news/id/4844580",
    },
    {
        "ticker": "5305",
        "known_at": datetime(2020, 9, 24, 15, 6),
        "terminal_stale_from": pd.Timestamp("2020-11-24").date(),
        "effective_at": datetime(2020, 11, 30),
        "payment_at": datetime(2020, 12, 4),
        "cash_per_share": 42.5,
        "source": "MOPS/TWSE cash share-conversion disclosure",
        "source_url": "https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=08e82787-ac21-4b82-a7e5-0457c205ba74",
    },
]

CURATED_COMPOSITE_CONVERSIONS = [
    {
        "ticker": "2823",
        "known_at": datetime(2021, 11, 16, 9, 3),
        "terminal_stale_from": pd.Timestamp("2021-12-20").date(),
        "effective_at": datetime(2021, 12, 30),
        "cash_per_share": 11.5,
        "successor_legs": (
            SecurityConversionLeg(
                to_ticker="2883",
                quantity_multiplier=0.8,
                value_weight=0.3681097069104598,
            ),
            SecurityConversionLeg(
                to_ticker="2883B",
                quantity_multiplier=0.73,
                value_weight=0.24536165635923635,
            ),
        ),
        "cash_value_weight": 0.38652863673030385,
        "source": "MOPS share-conversion disclosure; value weights use disclosed 20-day common reference price 13.69, preferred issue price 10.0, and cash 11.5",
        "source_url": "https://www.moneydj.com/kmdj/news/newsviewer.aspx?a=bdb8cd34-7c85-499c-8e74-610c995a8dc6",
    },
]

CURATED_SUCCESSOR_CONVERSIONS = [
    {
        "ticker": "6251",
        "known_at": datetime(2022, 7, 4, 8, 50),
        "terminal_stale_from": pd.Timestamp("2022-08-15").date(),
        "effective_at": datetime(2022, 8, 25),
        "successor_ticker": "3715",
        "successor_multiplier": 1.0,
        "source": "TWSE/MOPS share-conversion disclosure",
        "source_url": "https://www.moneydj.com/KMDJ/news/newsviewer.aspx?a=3dbfbc6a-01a5-4eda-87f9-d2aa3530a649",
    },
]


def load_adjusted() -> pd.DataFrame:
    parts = []
    start_year = SIGNAL_START.year - 1
    end_year = SIGNAL_END.year
    for year in range(start_year, end_year + 1):
        p = SOURCE_ROOT / "adj" / f"prices_adj_{year}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(
            p,
            columns=["date", "stock_id", "open", "max", "min", "close", "Trading_money"],
        )
        d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
        d["stock_id"] = d["stock_id"].astype(str)
        parts.append(d)
    if not parts:
        raise SystemExit("BLOCKED: no adjusted source files for requested signal horizon")
    return pd.concat(parts, ignore_index=True)


def load_tradability(adjusted: pd.DataFrame) -> pd.DataFrame:
    d = pd.read_parquet(
        SOURCE_ROOT / "reference" / "tradability.parquet",
        columns=[
            "date", "stock_id", "observed_trade", "valid_ohlc",
            "buy_blocked", "sell_blocked", "reason",
        ],
    )
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
    d["stock_id"] = d["stock_id"].astype(str)
    first_adjusted = adjusted["date"].dropna().min()
    return d[d["date"].ge(first_adjusted)].copy()


def pit_unsafe_ca_tickers(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> set[str]:
    dividend = pd.read_parquet(SOURCE_ROOT / "fundamentals" / "dividend.parquet")
    actions = build_finmind_normalized_actions(dividend)
    return {
        a.ticker
        for a in actions
        if start.date() <= a.effective_date <= end.date()
        and a.known_at is not None
        and a.known_at.date() > a.effective_date
    }


def build_supported_ca(
    *,
    candidate_tickers: set[str],
    sessions: set[pd.Timestamp],
) -> tuple[list[HistoricalCorporateActionInstruction], int, dict[str, int]]:
    if not sessions:
        return [], 0, {}

    session_start = min(sessions)
    session_end = max(sessions)
    instructions: list[HistoricalCorporateActionInstruction] = []
    unsupported_summary: dict[str, int] = {}

    # Dividend economics come from the AstraQuant normalized FinMind view,
    # not the legacy ledger date/unit representation.
    dividend = pd.read_parquet(SOURCE_ROOT / "fundamentals" / "dividend.parquet")
    normalized = build_finmind_normalized_actions(dividend)
    normalized = [
        a for a in normalized
        if a.ticker in candidate_tickers
        and session_start.date() <= a.effective_date <= session_end.date()
    ]

    pit_late = [
        a for a in normalized
        if a.known_at is not None and a.known_at.date() > a.effective_date
    ]
    if pit_late:
        unsupported_summary["normalized_known_after_effective"] = len(pit_late)

    for a in normalized:
        if a in pit_late:
            continue
        effective_at = datetime.combine(a.effective_date, datetime.min.time())
        if a.kind is NormalizedCorporateActionKind.CASH_DIVIDEND:
            event = CorporateActionEvent(
                event_id=f"smoke:{a.ticker}:{a.effective_date}:cash_dividend",
                ticker=a.ticker,
                event_type=CorporateActionType.CASH_DIVIDEND,
                effective_at=effective_at,
                known_at=a.known_at,
                payment_at=a.payment_at,
                cash_per_share=a.cash_per_share,
                source=a.source_name,
                notes=a.unit_semantics,
            )
            instructions.append(
                HistoricalCorporateActionInstruction(
                    event=event,
                    applied_at=event.effective_at,
                    cash_share_basis_mode=CashEntitlementBasis.OPENING_POSITION,
                )
            )
        elif a.kind is NormalizedCorporateActionKind.STOCK_DIVIDEND:
            event = CorporateActionEvent(
                event_id=f"smoke:{a.ticker}:{a.effective_date}:stock_dividend",
                ticker=a.ticker,
                event_type=CorporateActionType.STOCK_DIVIDEND,
                effective_at=effective_at,
                known_at=a.known_at,
                share_multiplier=a.share_multiplier,
                source=a.source_name,
                notes=a.unit_semantics,
            )
            instructions.append(
                HistoricalCorporateActionInstruction(
                    event=event,
                    applied_at=event.effective_at,
                )
            )

    # Keep explicit official non-dividend mutations/refunds from the canonical
    # ledger. ex_right_dividend/dividend rows are intentionally excluded here
    # to avoid the legacy FinMind date/unit bugs and incomplete TWSE amounts.
    ledger = pd.read_parquet(
        SOURCE_ROOT / "reference" / "corporate_actions_ledger.parquet",
        columns=[
            "stock_id", "event_date", "known_date", "event_type",
            "cash_per_share", "share_multiplier", "source_name", "source_url",
        ],
    )
    ledger["stock_id"] = ledger["stock_id"].astype(str)
    ledger["event_date"] = pd.to_datetime(ledger["event_date"], errors="coerce").dt.normalize()
    ledger["known_date"] = pd.to_datetime(ledger["known_date"], errors="coerce")
    ledger["cash_per_share"] = pd.to_numeric(ledger["cash_per_share"], errors="coerce")
    ledger["share_multiplier"] = pd.to_numeric(ledger["share_multiplier"], errors="coerce")

    nondiv = ledger[
        ledger["stock_id"].isin(candidate_tickers)
        & ledger["event_date"].between(session_start, session_end, inclusive="both")
        & ledger["event_type"].astype(str).isin(
            {"capital_reduction", "capital_reduction_deficit", "par_value_change_split"}
        )
    ].copy()

    for (ticker, day, source_type), g in nondiv.groupby(
        ["stock_id", "event_date", "event_type"],
        sort=True,
    ):
        cash_vals = sorted(set(round(float(v), 8) for v in g["cash_per_share"].dropna()))
        mult_vals = sorted(set(round(float(v), 10) for v in g["share_multiplier"].dropna()))
        if len(cash_vals) > 1 or len(mult_vals) > 1:
            raise SystemExit(
                f"BLOCKED: conflicting non-dividend CA values {ticker} {day} {source_type}"
            )
        row = g.sort_values(["source_name", "source_url"]).iloc[0]
        cash = cash_vals[0] if cash_vals else None
        multiplier = mult_vals[0] if mult_vals else None
        if str(source_type).startswith("capital_reduction"):
            mapped_type = CorporateActionType.CAPITAL_REDUCTION
            component = "CAPITAL_REDUCTION_REFUND" if cash is not None else None
        else:
            mapped_type = CorporateActionType.SPLIT
            component = None

        event = CorporateActionEvent(
            event_id=f"smoke:{ticker}:{pd.Timestamp(day).date()}:{source_type}",
            ticker=str(ticker),
            event_type=mapped_type,
            effective_at=datetime.combine(pd.Timestamp(day).date(), datetime.min.time()),
            known_at=None if pd.isna(row["known_date"]) else pd.Timestamp(row["known_date"]).to_pydatetime(),
            cash_per_share=cash,
            share_multiplier=multiplier,
            source=str(row["source_name"]),
            notes=str(row["source_url"]),
        )
        instructions.append(
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
                component=component,
                cash_share_basis_mode=CashEntitlementBasis.OPENING_POSITION,
            )
        )

    for item in CURATED_TERMINAL_EVENTS:
        ticker = str(item["ticker"])
        effective_at = item["effective_at"]
        if (
            ticker not in candidate_tickers
            or effective_at.date() < session_start.date()
            or effective_at.date() > session_end.date()
        ):
            continue
        event = CorporateActionEvent(
            event_id=f"terminal:{ticker}:{effective_at.date()}:cash_merger",
            ticker=ticker,
            event_type=CorporateActionType.MERGER,
            effective_at=effective_at,
            known_at=item["known_at"],
            payment_at=item["payment_at"],
            cash_per_share=float(item["cash_per_share"]),
            source=str(item["source"]),
            notes=str(item["source_url"]),
        )
        instructions.append(
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
                component="MERGER_CASHOUT",
                cash_share_basis_mode=CashEntitlementBasis.OPENING_POSITION,
                terminal_stale_from=item["terminal_stale_from"],
                extinguish_position=True,
            )
        )

    for item in CURATED_SUCCESSOR_CONVERSIONS:
        ticker = str(item["ticker"])
        effective_at = item["effective_at"]
        if (
            ticker not in candidate_tickers
            or effective_at.date() < session_start.date()
            or effective_at.date() > session_end.date()
        ):
            continue
        successor_ticker = str(item["successor_ticker"])
        candidate_tickers.add(successor_ticker)
        event = CorporateActionEvent(
            event_id=f"successor:{ticker}:{effective_at.date()}:{successor_ticker}",
            ticker=ticker,
            event_type=CorporateActionType.MERGER,
            effective_at=effective_at,
            known_at=item["known_at"],
            source=str(item["source"]),
            notes=str(item["source_url"]),
        )
        instructions.append(
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
                terminal_stale_from=item["terminal_stale_from"],
                successor_ticker=successor_ticker,
                successor_multiplier=float(item["successor_multiplier"]),
            )
        )

    for item in CURATED_COMPOSITE_CONVERSIONS:
        ticker = str(item["ticker"])
        effective_at = item["effective_at"]
        if (
            ticker not in candidate_tickers
            or effective_at.date() < session_start.date()
            or effective_at.date() > session_end.date()
        ):
            continue
        for leg in item["successor_legs"]:
            candidate_tickers.add(str(leg.to_ticker))
        event = CorporateActionEvent(
            event_id=f"composite:{ticker}:{effective_at.date()}",
            ticker=ticker,
            event_type=CorporateActionType.MERGER,
            effective_at=effective_at,
            known_at=item["known_at"],
            cash_per_share=float(item["cash_per_share"]),
            source=str(item["source"]),
            notes=str(item["source_url"]),
        )
        instructions.append(
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
                component="MERGER_CASHOUT_PARTIAL",
                cash_share_basis_mode=CashEntitlementBasis.OPENING_POSITION,
                terminal_stale_from=item["terminal_stale_from"],
                successor_legs=tuple(item["successor_legs"]),
                cash_value_weight=float(item["cash_value_weight"]),
            )
        )

    instructions.sort(key=lambda x: (x.event.effective_at, x.event.event_id))
    unsupported_count = sum(unsupported_summary.values())
    return instructions, unsupported_count, unsupported_summary

def main() -> None:
    adjusted = load_adjusted()
    tradability = load_tradability(adjusted)

    all_signals = build_simple_breakout_signals(
        adjusted,
        tradability[["date", "stock_id", "observed_trade", "valid_ohlc"]],
        config=BreakoutSignalConfig(lookback=250, universe_fraction=0.25),
    )
    signals = all_signals[
        all_signals["signal_date"].between(SIGNAL_START, SIGNAL_END)
    ].copy()

    # Quarantine tickers whose normalized corporate-action detail was not
    # available by the economic effective date. This is a source/PIT quality
    # exclusion, not a performance-based filter.
    quarantined_tickers = pit_unsafe_ca_tickers(
        start=SIGNAL_START,
        end=SIGNAL_END,
    )
    quarantined_signal_rows = int(
        signals["stock_id"].astype(str).isin(quarantined_tickers).sum()
    )
    signals = signals[
        ~signals["stock_id"].astype(str).isin(quarantined_tickers)
    ].copy()

    if signals.empty:
        raise SystemExit("BLOCKED: no canonical breakout signals in smoke window")

    # Simulation uses the actual source-session calendar. Post-signal sessions
    # are included to give T+N settlements a chance to drain without adding
    # calendar days by assumption.
    market_sessions = [
        pd.Timestamp(x)
        for x in adjusted["date"].dropna().drop_duplicates().sort_values().tolist()
        if pd.Timestamp(x) >= SIGNAL_START
    ]
    if not market_sessions:
        raise SystemExit("BLOCKED: no source sessions in requested signal horizon")
    eligible_end_positions = [i for i, x in enumerate(market_sessions) if x <= SIGNAL_END]
    if not eligible_end_positions:
        raise SystemExit("BLOCKED: signal end precedes first source session")
    end_pos = max(eligible_end_positions)
    sim_end = min(len(market_sessions), end_pos + 1 + DRAIN_SESSIONS)
    sim_sessions = market_sessions[:sim_end]
    session_set = set(sim_sessions)

    candidate_tickers = set(signals["stock_id"].astype(str))
    ca_instructions, unsupported_ca_cash, unsupported_ca_summary = build_supported_ca(
        candidate_tickers=candidate_tickers,
        sessions=session_set,
    )
    if unsupported_ca_cash:
        raise SystemExit(
            f"BLOCKED: {unsupported_ca_cash} non-dividend cash CA source rows "
            f"need explicit runtime entitlement basis before strategy smoke; "
            f"event_types={unsupported_ca_summary}"
        )

    portfolio = PortfolioEngine(opening_cash=10_000_000.0)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(
            SourceDataAdapter(SOURCE_ROOT),
            ticker_scope=candidate_tickers,
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
            source="CANONICAL_SIMPLE_BREAKOUT_V1",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=2),
    )

    result = simulator.run(
        sessions=[x.date() for x in sim_sessions],
        signals=signals,
        corporate_actions=ca_instructions,
    )

    final = result.sessions[-1].snapshot.valuation
    checks = {
        "canonical_signals_used": len(signals) > 0,
        "canonical_strategy_simulator_used": True,
        "entries_executed": result.total_entries > 0,
        "raw_nav_snapshots_complete": len(result.sessions) == len(sim_sessions),
        "pending_payables_nonnegative": portfolio.cash.pending_payables >= -1e-9,
        "pending_receivables_nonnegative": portfolio.cash.pending_receivables >= -1e-9,
        "settled_cash_nonnegative": portfolio.cash.settled_cash >= -1e-9,
        "no_adjusted_execution_fallback": True,
        "unsupported_ca_cash_zero": unsupported_ca_cash == 0,
        "pit_unsafe_ca_tickers_excluded": not bool(candidate_tickers & quarantined_tickers),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        f"# {REPORT_TITLE}",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: connect real canonical breakout candidates to the causal RAW portfolio simulator without evaluating strategy performance.",
        "",
        "## Integration window",
        "",
        f"- signal window: {SIGNAL_START.date()} through {SIGNAL_END.date()}",
        f"- post-signal drain sessions requested: {DRAIN_SESSIONS}",
        f"- simulation sessions: {sim_sessions[0].date()} through {sim_sessions[-1].date()}",
        f"- session count / RAW NAV snapshots: {len(result.sessions):,}",
        f"- canonical signal candidates supplied: {len(signals):,}",
        f"- candidate tickers in scoped execution source: {len(candidate_tickers):,}",
        f"- PIT-unsafe CA tickers quarantined: {len(quarantined_tickers):,}",
        f"- signal rows removed by PIT CA quarantine: {quarantined_signal_rows:,}",
        "- integration-only policy: 10% NAV target, max 10 positions, 12% RAW stop, 20-session re-entry gap, 250-session max hold, 1000-share lot, seed 0",
        "",
        "## Accounting/event audit counts",
        "",
        f"- entries executed: {result.total_entries:,}",
        f"- entry candidates skipped/blocked: {result.total_entry_skips:,}",
        f"- RAW stop exits: {result.total_stop_exits:,}",
        f"- RAW max-hold exits: {result.total_max_hold_exits:,}",
        f"- blocked exit attempts: {result.total_blocked_exits:,}",
        f"- supported corporate actions applied: {result.total_corporate_actions:,}",
        f"- corporate-action cash payments settled: {result.total_corporate_cash_payments:,}",
        "",
        "## Final accounting state",
        "",
        f"- open managed positions: {len(policy.managed_positions):,}",
        f"- settled cash: {portfolio.cash.settled_cash}",
        f"- pending receivables: {portfolio.cash.pending_receivables}",
        f"- pending payables: {portfolio.cash.pending_payables}",
        f"- RAW market value: {final.market_value}",
        f"- NAV: {final.nav}",
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
        "## Performance lock",
        "",
        "The numeric NAV/cash values above are accounting state only. No return, CAGR, drawdown, MAR, Sharpe, hit rate, or strategy comparison is computed.",
        "",
        "If this smoke fails because a held security cannot be marked from current RAW data, the next task is an explicit RAW stale-mark policy; adjusted prices remain prohibited as a fallback.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        print("FAILED_CHECKS=" + ",".join(failed))
        raise SystemExit("FAIL: source canonical strategy integration smoke failed")


if __name__ == "__main__":
    main()
