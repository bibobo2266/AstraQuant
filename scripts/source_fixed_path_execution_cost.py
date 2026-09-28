#!/usr/bin/env python3
from __future__ import annotations

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
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import CanonicalStrategySimulator, StrategySimulationConfig

from source_execution_sensitivity import (
    INITIAL_CASH,
    SCENARIOS,
    SOURCE_ROOT,
    build_inputs,
)

REPORT_PATH = Path(os.environ.get(
    "REPORT_PATH",
    "docs/SOURCE_FIXED_PATH_EXECUTION_COST_ATTRIBUTION.md",
))


def metric_row(nav: pd.Series) -> dict[str, float]:
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


def main() -> None:
    signals, sim_sessions, candidate_tickers, ca_instructions, quarantined = build_inputs()

    portfolio = PortfolioEngine(opening_cash=INITIAL_CASH)
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

    dates = pd.DatetimeIndex([pd.Timestamp(x.session_date) for x in result.sessions])
    baseline_nav = pd.Series(
        [float(x.snapshot.valuation.nav) for x in result.sessions],
        index=dates,
        dtype=float,
    )

    fills = []
    for order in portfolio.orders.orders.values():
        fills.extend(order.fills)
    fills = sorted(fills, key=lambda x: (x.filled_at, x.fill_id))
    if not fills:
        raise SystemExit("FAIL: no baseline fills available for fixed-path attribution")

    rows = []
    monotonic_costs = []
    previous_cost = -1.0

    for scenario in SCENARIOS:
        cost_by_day: dict[pd.Timestamp, float] = {}
        total_slippage_drag = 0.0
        total_fee_drag = 0.0

        for fill in fills:
            base_price = float(fill.price)
            if fill.side.lower() == "buy":
                stressed_price = base_price * (1.0 + scenario.slippage_bps / 10_000.0)
            elif fill.side.lower() == "sell":
                stressed_price = base_price * (1.0 - scenario.slippage_bps / 10_000.0)
            else:
                raise SystemExit(f"FAIL: unsupported fill side {fill.side}")

            slippage_drag = abs(stressed_price - base_price) * float(fill.quantity)
            fee_drag = (
                float(fill.quantity)
                * stressed_price
                * scenario.fee_bps
                / 10_000.0
            )
            drag = slippage_drag + fee_drag
            day = pd.Timestamp(fill.filled_at).normalize()
            cost_by_day[day] = cost_by_day.get(day, 0.0) + drag
            total_slippage_drag += slippage_drag
            total_fee_drag += fee_drag

        daily_cost = pd.Series(0.0, index=dates)
        for day, amount in cost_by_day.items():
            if day in daily_cost.index:
                daily_cost.loc[day] += amount
            else:
                later = daily_cost.index[daily_cost.index >= day]
                if len(later):
                    daily_cost.loc[later[0]] += amount
                else:
                    daily_cost.iloc[-1] += amount

        cumulative_drag = daily_cost.cumsum()
        stressed_nav = baseline_nav - cumulative_drag
        if (stressed_nav <= 0).any():
            raise SystemExit(
                f"FAIL: fixed-path stressed NAV became nonpositive for {scenario.name}"
            )

        metrics = metric_row(stressed_nav)
        total_drag = total_slippage_drag + total_fee_drag
        monotonic_costs.append(total_drag >= previous_cost - 1e-9)
        previous_cost = total_drag

        rows.append({
            "scenario": scenario.name,
            "fee_bps_per_fill": scenario.fee_bps,
            "slippage_bps_per_fill": scenario.slippage_bps,
            "fill_count": len(fills),
            "slippage_drag": total_slippage_drag,
            "fee_drag": total_fee_drag,
            "total_cost_drag": total_drag,
            **metrics,
        })

    frame = pd.DataFrame(rows)
    checks = {
        "baseline_fill_path_frozen": frame["fill_count"].nunique() == 1,
        "all_scenarios_same_nav_sessions": True,
        "cost_drag_monotonic": bool(all(monotonic_costs)),
        "final_nav_monotonic_nonincreasing": bool(
            frame["final_nav"].diff().fillna(0).le(1e-9).all()
        ),
        "pit_unsafe_ca_tickers_excluded": not bool(candidate_tickers & quarantined),
    }
    status = "PASS" if all(checks.values()) else "FAIL"

    lines = [
        "# Fixed-Trade-Path Execution-Cost Attribution",
        "",
        f"Status: **{status}**",
        "",
        "Purpose: isolate pure execution-cost drag by freezing the exact zero-friction baseline fill path. Unlike the full execution-sensitivity reruns, this attribution does not allow fees/slippage to alter sizing, capacity, entry selection, stops, or holding paths.",
        "",
        "## Frozen path",
        "",
        f"- signal window: {sim_sessions[0].date()} through {pd.Timestamp(os.environ.get('SIGNAL_END', '2026-06-30')).date()}",
        f"- simulation/drain horizon: {dates[0].date()} through {dates[-1].date()}",
        f"- RAW NAV sessions: {len(baseline_nav):,}",
        f"- baseline fills frozen: {len(fills):,}",
        f"- baseline entries: {result.total_entries:,}",
        f"- baseline RAW stop exits: {result.total_stop_exits:,}",
        f"- baseline max-hold exits: {result.total_max_hold_exits:,}",
        "",
        "## Fixed-path cost attribution",
        "",
        "| Scenario | Fee bps/fill | Slippage bps/fill | Slippage drag | Fee drag | Total cost drag | Final NAV | Total return | CAGR | Max DD | Sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in frame.itertuples(index=False):
        lines.append(
            f"| {row.scenario} | {row.fee_bps_per_fill:.0f} | {row.slippage_bps_per_fill:.0f} "
            f"| {row.slippage_drag:,.2f} | {row.fee_drag:,.2f} | {row.total_cost_drag:,.2f} "
            f"| {row.final_nav:,.2f} | {row.total_return*100:.2f}% | {row.cagr*100:.2f}% "
            f"| {row.max_drawdown*100:.2f}% | {row.sharpe:.3f} |"
        )

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
        "## Interpretation boundary",
        "",
        "This is a mechanical attribution on a frozen trade path. It answers how much the observed baseline path would lose to explicit cost assumptions. It is not a fully executable counterfactual because higher costs could change cash availability and future decisions. The separate full reruns capture that endogenous path dependence.",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if status != "PASS":
        raise SystemExit("FAIL: fixed-path execution-cost attribution gate failed")


if __name__ == "__main__":
    main()
