#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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
from astraquant.portfolio.policy import CapacitySelectionRule, PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationConfig
from astraquant.portfolio.trade_reconstruction import reconstruct_fifo_trades

from source_strategy_integration_smoke import (
    DRAIN_SESSIONS,
    SIGNAL_END,
    SIGNAL_START,
    build_supported_ca,
    load_adjusted,
    load_tradability,
)

SOURCE_ROOT = Path(os.environ.get("SOURCE_ROOT", "source_runtime/minervini_picks/data")).resolve()
REPORT_PATH = Path(os.environ.get("REPORT_PATH", "docs/SOURCE_BREAKOUT_STRENGTH_FIFO_ATTRIBUTION.md"))
EXCLUSIONS_PATH = Path(os.environ.get("EXCLUSIONS_PATH", "docs/SOURCE_CA_PIT_EXCLUSIONS.csv"))
EXPECTED_EXCLUSIONS_SHA256 = "379d58f6a8aa06b1e020d56911930f4bc01861d3eeca109613d9e5b1e490d134"
INITIAL_CASH = 10_000_000.0
STOP_FRACTION = 0.12
BOOTSTRAP_REPS = 5000
BOOTSTRAP_SEED = 20260928

RULES = (
    ("ticker_asc", CapacitySelectionRule.TICKER_ASC),
    ("turnover_desc", CapacitySelectionRule.TURNOVER_DESC),
    ("turnover_asc", CapacitySelectionRule.TURNOVER_ASC),
    ("breakout_excess_desc", CapacitySelectionRule.BREAKOUT_EXCESS_DESC),
    ("breakout_excess_asc", CapacitySelectionRule.BREAKOUT_EXCESS_ASC),
    ("hash_asc", CapacitySelectionRule.HASH_ASC),
)


def _path_metrics(nav: pd.Series) -> dict[str, float]:
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


def _all_fills(portfolio: PortfolioEngine):
    seen = {}
    for position in portfolio.positions.positions.values():
        for fill in position.fills:
            prior = seen.get(fill.fill_id)
            if prior is not None and prior != fill:
                raise SystemExit(f"FAIL: conflicting duplicate fill id {fill.fill_id}")
            seen[fill.fill_id] = fill
    return [seen[key] for key in sorted(seen)]


def _trade_frame(portfolio: PortfolioEngine) -> pd.DataFrame:
    ca = portfolio.corporate_actions
    cash_entitlements = list(ca.cash_entitlement_receivables.values()) + list(
        ca.completed_cash_entitlements.values()
    )
    reconstructed = reconstruct_fifo_trades(
        fills=_all_fills(portfolio),
        share_mutations=ca.share_mutations.values(),
        security_conversions=ca.security_conversions.values(),
        composite_conversions=ca.composite_conversions.values(),
        position_extinguishments=ca.position_extinguishments.values(),
        cash_entitlements=cash_entitlements,
    )

    open_source_ids = {lot.source_fill_id for lot in reconstructed.open_lots}
    rows = []
    for lot in reconstructed.closed_lots:
        rows.append(
            {
                "source_fill_id": lot.source_fill_id,
                "entry_at": pd.Timestamp(lot.entry_at),
                "exit_at": pd.Timestamp(lot.exit_at),
                "entry_ticker": lot.entry_ticker,
                "exit_ticker": lot.exit_ticker,
                "quantity": float(lot.quantity),
                "entry_cost": float(lot.entry_price_with_fees) * float(lot.quantity),
                "realized_pnl": float(lot.realized_pnl),
                "exit_kind": lot.exit_kind,
            }
        )
    lots = pd.DataFrame(rows)
    if lots.empty:
        raise SystemExit("FAIL: no closed FIFO lots reconstructed")

    grouped_rows = []
    for source_fill_id, group in lots.groupby("source_fill_id", sort=True):
        if source_fill_id in open_source_ids:
            continue
        cost = float(group["entry_cost"].sum())
        pnl = float(group["realized_pnl"].sum())
        grouped_rows.append(
            {
                "source_fill_id": source_fill_id,
                "entry_at": group["entry_at"].min(),
                "exit_at": group["exit_at"].max(),
                "entry_ticker": "|".join(sorted(set(group["entry_ticker"].astype(str)))),
                "exit_ticker": "|".join(sorted(set(group["exit_ticker"].astype(str)))),
                "entry_cost": cost,
                "realized_pnl": pnl,
                "return_on_cost": pnl / cost if cost > 0 else float("nan"),
                "exit_kind": "|".join(sorted(set(group["exit_kind"].astype(str)))),
            }
        )
    trades = pd.DataFrame(grouped_rows)
    if trades.empty or trades["return_on_cost"].isna().any():
        raise SystemExit("FAIL: closed-trade reconstruction is empty or invalid")
    trades["entry_year"] = pd.to_datetime(trades["entry_at"]).dt.year.astype(int)
    trades.attrs["open_lots"] = len(reconstructed.open_lots)
    trades.attrs["cash_extinguishment_lots"] = int(
        (lots["exit_kind"] == "CASH_EXTINGUISHMENT").sum()
    )
    return trades


def _trade_metrics(trades: pd.DataFrame) -> dict[str, float]:
    r = trades["return_on_cost"].astype(float)
    winners = r[r > 0]
    losers = r[r < 0]
    mean_winner = float(winners.mean()) if len(winners) else float("nan")
    mean_loser = float(losers.mean()) if len(losers) else float("nan")
    payoff = (
        mean_winner / abs(mean_loser)
        if len(winners) and len(losers) and mean_loser != 0
        else float("nan")
    )
    expectancy = float(r.mean())
    return {
        "closed_trades": int(len(trades)),
        "win_rate": float((r > 0).mean()),
        "mean_winner": mean_winner,
        "mean_loser": mean_loser,
        "payoff_ratio": payoff,
        "expectancy": expectancy,
        "stop_normalized_expectancy": expectancy / STOP_FRACTION,
        "median_trade_return": float(r.median()),
        "open_lots": int(trades.attrs.get("open_lots", 0)),
        "cash_extinguishment_lots": int(trades.attrs.get("cash_extinguishment_lots", 0)),
    }


def _year_block_bootstrap_mean(trades: pd.DataFrame, *, seed: int) -> tuple[float, float, int]:
    years = sorted(trades["entry_year"].unique().tolist())
    if len(years) < 2:
        return float("nan"), float("nan"), len(years)
    by_year = {
        year: trades.loc[trades["entry_year"].eq(year), "return_on_cost"].to_numpy(float)
        for year in years
    }
    rng = np.random.default_rng(seed)
    values = np.empty(BOOTSTRAP_REPS, dtype=float)
    for i in range(BOOTSTRAP_REPS):
        sampled = rng.choice(np.array(years), size=len(years), replace=True)
        draw = np.concatenate([by_year[int(year)] for year in sampled])
        values[i] = float(draw.mean())
    low, high = np.quantile(values, [0.025, 0.975])
    return float(low), float(high), len(years)


def _paired_year_block_difference(
    first: pd.DataFrame,
    second: pd.DataFrame,
) -> tuple[float, float, float, int]:
    years = sorted(set(first["entry_year"]) & set(second["entry_year"]))
    if len(years) < 2:
        return float("nan"), float("nan"), float("nan"), len(years)
    first_by_year = {
        year: first.loc[first["entry_year"].eq(year), "return_on_cost"].to_numpy(float)
        for year in years
    }
    second_by_year = {
        year: second.loc[second["entry_year"].eq(year), "return_on_cost"].to_numpy(float)
        for year in years
    }
    observed = float(first["return_on_cost"].mean() - second["return_on_cost"].mean())
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    values = np.empty(BOOTSTRAP_REPS, dtype=float)
    for i in range(BOOTSTRAP_REPS):
        sampled = rng.choice(np.array(years), size=len(years), replace=True)
        a = np.concatenate([first_by_year[int(year)] for year in sampled])
        b = np.concatenate([second_by_year[int(year)] for year in sampled])
        values[i] = float(a.mean() - b.mean())
    low, high = np.quantile(values, [0.025, 0.975])
    return observed, float(low), float(high), len(years)


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
            stop_fraction=STOP_FRACTION,
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
            source=f"BREAKOUT_STRENGTH_FIFO:{name}",
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

    trades = _trade_frame(portfolio)
    trade_metrics = _trade_metrics(trades)
    ci_low, ci_high, bootstrap_year_blocks = _year_block_bootstrap_mean(
        trades,
        seed=BOOTSTRAP_SEED + [x[0] for x in RULES].index(name),
    )
    row = {
        "rule": name,
        "entries": result.total_entries,
        "stop_exits": result.total_stop_exits,
        "max_hold_exits": result.total_max_hold_exits,
        "blocked_exits": result.total_blocked_exits,
        "capacity_overflow_sessions": result.total_capacity_overflow_sessions,
        "capacity_only_rejections": result.total_capacity_rejections,
        "expectancy_ci_low": ci_low,
        "expectancy_ci_high": ci_high,
        "bootstrap_year_blocks": bootstrap_year_blocks,
        **_path_metrics(nav),
        **trade_metrics,
    }
    return row, trades


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

    rows = []
    trade_frames = {}
    for name, rule in RULES:
        row, trades = _run_rule(
            name=name,
            rule=rule,
            signals=signals,
            sim_sessions=sim_sessions,
            ca_instructions=ca_instructions,
            ticker_scope=ticker_scope,
        )
        rows.append(row)
        trade_frames[name] = trades

    frame = pd.DataFrame(rows)
    desc = frame[frame["rule"].eq("breakout_excess_desc")].iloc[0]
    asc = frame[frame["rule"].eq("breakout_excess_asc")].iloc[0]
    neutral = frame[frame["rule"].isin(["ticker_asc", "hash_asc"])]
    diff_obs, diff_low, diff_high, paired_year_blocks = _paired_year_block_difference(
        trade_frames["breakout_excess_desc"],
        trade_frames["hash_asc"],
    )

    checks = {
        "frozen_exclusion_hash_matches": True,
        "all_six_declared_rules_complete": len(frame) == len(RULES),
        "common_support_exclusion_active": not bool(ticker_scope & excluded),
        "ranking_metadata_complete": not bool(signals[["turnover_value", "breakout_excess"]].isna().any().any()),
        "all_nav_positive": bool(frame["final_nav"].gt(0).all()),
        "fifo_closed_trades_present_all_rules": bool(frame["closed_trades"].gt(0).all()),
        "no_new_ca_blocker": unsupported_count == 0,
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Breakout-Strength Direction + CA-Aware FIFO Attribution",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: follow up P2-061 without interpreting its path-only result prematurely. This diagnostic adds the reverse breakout-strength rule, reconstructs single-trade outcomes through canonical fills plus corporate-action share mutations, successor conversions, and cash-extinguishment entitlements, and adds a fixed calendar-year block-bootstrap uncertainty scale.",
        "",
        "## Rule provenance",
        "",
        "- ticker_asc, turnover_desc, turnover_asc, breakout_excess_desc, hash_asc were preregistered in P2-061 before any result was observed.",
        "- breakout_excess_asc was added in P2-062 AFTER the P2-061 result was observed, at external-reviewer request, as the symmetric counterpart required to distinguish directional signal information from dispersion-selection effects. It is NOT preregistered-blind and must not be represented as such.",
        "",
        "## Frozen design",
        "",
        "- P2-060 exclusion ledger is unchanged and hash-gated.",
        "- signal definition, 250-session lookback, top-25% turnover universe, RAW execution/accounting, 10% NAV target, 10-position cap, 12% stop, 20-session re-entry, 250-session max hold, 1000-share lot, and zero fee/slippage are unchanged.",
        "- six deterministic rules are rerun because P2-061 did not persist fills/trade ledgers; FIFO trade statistics cannot be recovered from its aggregate report alone.",
        "- new directional falsification rule: weakest causal breakout excess first (breakout_excess_asc).",
        "- trade unit: one entry fill, aggregated across any FIFO lot fragments until fully closed. Partially open entry lots are excluded from closed-trade statistics and counted separately.",
        "- cash mergers close lots from explicit cash-entitlement economics at the extinguishment effective date; no synthetic market sell fill is created.",
        f"- uncertainty scale: {BOOTSTRAP_REPS:,} calendar-year block-bootstrap replications, fixed seed {BOOTSTRAP_SEED}. The number of resamples controls Monte Carlo precision; the effective block count is the number of distinct calendar-year blocks, not 5,000.",
        "",
        "## Path + single-trade results",
        "",
        "| Rule | CAGR | Max DD | Sharpe | Entries | Closed trades | Open lots | Win rate | Payoff | Expectancy | Stop-normalized expectancy | 95% year-block CI | Cash-extinguishment lots |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.rule} | {row.cagr*100:.2f}% | {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} "
            f"| {row.entries:,} | {int(row.closed_trades):,} | {int(row.open_lots):,} "
            f"| {row.win_rate*100:.2f}% | {row.payoff_ratio:.3f} | {row.expectancy*100:.2f}% "
            f"| {row.stop_normalized_expectancy:.3f} | [{row.expectancy_ci_low*100:.2f}%, {row.expectancy_ci_high*100:.2f}%] "
            f"| {int(row.cash_extinguishment_lots):,} |"
        )

    lines += [
        "",
        "## Directional comparison",
        "",
        f"- strongest-breakout-first CAGR: {desc['cagr']*100:.2f}%",
        f"- weakest-breakout-first CAGR: {asc['cagr']*100:.2f}%",
        f"- neutral deterministic CAGR range (ticker/hash): {neutral['cagr'].min()*100:.2f}% to {neutral['cagr'].max()*100:.2f}%",
        f"- strongest-breakout-first single-trade expectancy: {desc['expectancy']*100:.2f}%",
        f"- weakest-breakout-first single-trade expectancy: {asc['expectancy']*100:.2f}%",
        f"- neutral deterministic single-trade expectancy range (ticker/hash): {neutral['expectancy'].min()*100:.2f}% to {neutral['expectancy'].max()*100:.2f}%",
        f"- strongest-breakout-first minus hash single-trade expectancy difference: {diff_obs*100:.2f} percentage points",
        f"- paired calendar-year block-bootstrap 95% interval for that difference: [{diff_low*100:.2f}, {diff_high*100:.2f}] percentage points",
        f"- paired bootstrap effective calendar-year blocks: {paired_year_blocks}; resamples: {BOOTSTRAP_REPS:,}",
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
        "This is an attribution/falsification diagnostic, not a promotion test. No deterministic rule is selected, no strategy parameter is changed, and locked OOS remains locked.",
        "",
        "The year-block bootstrap is a descriptive uncertainty scale, not a claim that trades are independent or that the interval has exact frequentist coverage under portfolio dependence. Its effective information count is the number of calendar-year blocks (reported above), while 5,000 is only the number of Monte Carlo resamples. Its purpose is to avoid treating one deterministic CAGR spread as self-interpreting.",
        "",
        "Closed-trade expectancy is return on entry cost. Stop-normalized expectancy means closed-trade expectancy divided by the frozen 12% stop fraction; it is not realized R because realized losses need not equal the stop fraction.",
        "",
        "External validity remains limited to the P2-060 common-support sub-universe, which excludes 355 of 1,986 eligible-universe tickers (17.9%).",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if status != "PASS":
        raise SystemExit("FAIL: breakout-strength FIFO attribution operational gate failed")


if __name__ == "__main__":
    main()
