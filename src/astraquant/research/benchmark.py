from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
import pandas as pd

from astraquant.portfolio.models import Fill
from astraquant.portfolio.performance_reporting import TradeReport


@dataclass(frozen=True)
class PathStatistics:
    total_return: float
    cagr: float
    max_drawdown: float
    sharpe: float


@dataclass(frozen=True)
class BenchmarkComparison:
    benchmark_nav: pd.Series
    cumulative_excess_return: float
    daily_return_correlation: float
    beta: float
    max_drawdown_difference: float
    trade_count: int
    annualized_gross_turnover: float
    average_holding_days: float
    strategy_path: PathStatistics
    benchmark_path: PathStatistics


def _normalized_nav(nav: pd.Series) -> pd.Series:
    out = pd.Series(nav, dtype=float).copy()
    out.index = pd.to_datetime(out.index, errors="coerce").normalize()
    if out.index.isna().any():
        raise ValueError("NAV index contains invalid dates")
    if out.index.duplicated().any():
        raise ValueError("NAV index contains duplicate dates")
    out = out.sort_index()
    if out.empty or (out <= 0).any():
        raise ValueError("NAV must be non-empty and positive")
    return out


def path_statistics(nav: pd.Series) -> PathStatistics:
    nav = _normalized_nav(nav)
    returns = nav.pct_change().dropna()
    years = (nav.index[-1] - nav.index[0]).days / 365.2425
    cagr = (
        (float(nav.iloc[-1]) / float(nav.iloc[0])) ** (1.0 / years) - 1.0
        if years > 0
        else float("nan")
    )
    drawdown = nav / nav.cummax() - 1.0
    std = float(returns.std(ddof=1)) if len(returns) > 1 else float("nan")
    sharpe = (
        float(returns.mean() / std * math.sqrt(252))
        if len(returns) > 1 and np.isfinite(std) and std > 0
        else float("nan")
    )
    return PathStatistics(
        total_return=float(nav.iloc[-1] / nav.iloc[0] - 1.0),
        cagr=float(cagr),
        max_drawdown=float(drawdown.min()),
        sharpe=sharpe,
    )


def load_finmind_total_return_index(
    path: str | Path,
    *,
    stock_id: str = "TAIEX",
) -> pd.Series:
    frame = pd.read_parquet(path)
    if "date" not in frame.columns:
        raise ValueError("total-return index requires date column")
    if "stock_id" in frame.columns:
        frame = frame[frame["stock_id"].astype(str).eq(str(stock_id))].copy()
    value_candidates = [c for c in ("price", "close", "value", "index") if c in frame.columns]
    if len(value_candidates) != 1:
        raise ValueError(
            "total-return index must expose exactly one recognized value column "
            f"(price/close/value/index); found {value_candidates}"
        )
    value_col = value_candidates[0]
    out = frame[["date", value_col]].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out = out.dropna(subset=["date", value_col])
    if out["date"].duplicated().any():
        raise ValueError("total-return index contains duplicate dates")
    out = out.sort_values("date")
    if out.empty or (out[value_col] <= 0).any():
        raise ValueError("total-return index must be non-empty and positive")
    return pd.Series(out[value_col].to_numpy(float), index=out["date"], name="total_return_index")


def build_buy_hold_benchmark_nav(
    total_return_index: pd.Series,
    *,
    strategy_dates,
    initial_cash: float,
) -> pd.Series:
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    tri = pd.Series(total_return_index, dtype=float).copy()
    tri.index = pd.to_datetime(tri.index, errors="coerce").normalize()
    if tri.index.isna().any() or tri.index.duplicated().any():
        raise ValueError("benchmark index dates must be valid and unique")
    tri = tri.sort_index()

    dates = pd.DatetimeIndex(pd.to_datetime(strategy_dates)).normalize()
    missing = dates.difference(tri.index)
    if len(missing):
        raise ValueError(
            "benchmark missing strategy trading dates: "
            + ",".join(str(x.date()) for x in missing[:10])
        )
    aligned = tri.reindex(dates)
    base = float(aligned.iloc[0])
    nav = initial_cash * aligned / base
    nav.name = "benchmark_nav"
    return nav.astype(float)


def annualized_gross_turnover(
    fills: tuple[Fill, ...] | list[Fill],
    *,
    strategy_nav: pd.Series,
) -> float:
    nav = _normalized_nav(strategy_nav)
    years = (nav.index[-1] - nav.index[0]).days / 365.2425
    if years <= 0:
        return float("nan")
    gross_notional = sum(
        abs(float(fill.quantity) * float(fill.price)) for fill in fills
    )
    return float(gross_notional / float(nav.mean()) / years)


def compare_strategy_to_total_return_benchmark(
    *,
    strategy_nav: pd.Series,
    total_return_index: pd.Series,
    initial_cash: float,
    fills: tuple[Fill, ...] | list[Fill],
    trade_report: TradeReport,
) -> BenchmarkComparison:
    strategy = _normalized_nav(strategy_nav)
    benchmark = build_buy_hold_benchmark_nav(
        total_return_index,
        strategy_dates=strategy.index,
        initial_cash=initial_cash,
    )
    benchmark = benchmark.reindex(strategy.index)

    strategy_returns = strategy.pct_change().dropna()
    benchmark_returns = benchmark.pct_change().dropna()
    aligned = pd.concat(
        [
            strategy_returns.rename("strategy"),
            benchmark_returns.rename("benchmark"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    correlation = (
        float(aligned["strategy"].corr(aligned["benchmark"]))
        if len(aligned) > 1
        else float("nan")
    )
    benchmark_var = float(aligned["benchmark"].var(ddof=1)) if len(aligned) > 1 else float("nan")
    beta = (
        float(aligned[["strategy", "benchmark"]].cov().iloc[0, 1] / benchmark_var)
        if np.isfinite(benchmark_var) and benchmark_var > 0
        else float("nan")
    )

    strategy_path = path_statistics(strategy)
    benchmark_path = path_statistics(benchmark)
    return BenchmarkComparison(
        benchmark_nav=benchmark,
        cumulative_excess_return=(
            strategy_path.total_return - benchmark_path.total_return
        ),
        daily_return_correlation=correlation,
        beta=beta,
        max_drawdown_difference=(
            strategy_path.max_drawdown - benchmark_path.max_drawdown
        ),
        trade_count=trade_report.statistics.n,
        annualized_gross_turnover=annualized_gross_turnover(
            fills,
            strategy_nav=strategy,
        ),
        average_holding_days=trade_report.statistics.average_holding_days,
        strategy_path=strategy_path,
        benchmark_path=benchmark_path,
    )


BENCHMARK_INTERPRETATION_TW = (
    "輸給基準不是淘汰標準。本專案的目的是尋找 0050 以外的機會，"
    "評估重點是「超額有多大、代價是什麼、與大盤的相關性多低」。"
    "一條報酬較低但相關性低的策略，配置價值可能高於報酬較高"
    "但高度同向的策略。不得以「未跑贏大盤」為由停止研究某條訊號。"
)


def _pct_text(value: float) -> str:
    return "n/a" if pd.isna(value) else f"{value * 100:.2f}%"


def _num_text(value: float, digits: int = 3) -> str:
    return "n/a" if pd.isna(value) else f"{value:.{digits}f}"


def render_benchmark_report_sections(
    *,
    trade_report: TradeReport,
    comparison: BenchmarkComparison,
) -> list[str]:
    """Render the canonical benchmark-aware report blocks.

    The order is governance-significant: trade-level evidence first, excess/cost
    second, and portfolio path statistics only as an appendix. Benchmark rows
    never appear in the trade-level table because buy-and-hold has no comparable
    closed-trade concept.
    """
    stats = trade_report.statistics
    unverified_terminal = sum(
        "UNVERIFIED_TERMINAL_CASHOUT" in trade.exit_components
        for trade in trade_report.closed_trades
    )
    unverified_share = (
        unverified_terminal / stats.n if stats.n else float("nan")
    )
    return [
        "## 一、單筆層（主表）",
        "",
        "| Metric | Strategy |",
        "|---|---:|",
        f"| Closed trades n | {stats.n:,} |",
        f"| Win rate | {_pct_text(stats.win_rate)} |",
        f"| Average win | {_pct_text(stats.average_win)} |",
        f"| Average loss | {_pct_text(stats.average_loss)} |",
        f"| Payoff ratio | {_num_text(stats.payoff_ratio)} |",
        f"| Expectancy per trade | {_pct_text(stats.expectancy)} |",
        (
            "| Closed trades involving UNVERIFIED_TERMINAL_CASHOUT | "
            f"{unverified_terminal:,} ({_pct_text(unverified_share)}) |"
        ),
        "",
        (
            "Open FIFO lots are reported separately and excluded from the table "
            f"above: **{len(trade_report.reconstruction.open_lots):,}** open lots."
        ),
        "",
        "## 二、超額與代價",
        "",
        "| Metric | Value |",
        "|---|---:|",
        (
            "| Cumulative excess return (strategy - benchmark) | "
            f"{_pct_text(comparison.cumulative_excess_return)} |"
        ),
        f"| Daily-return correlation | {_num_text(comparison.daily_return_correlation)} |",
        f"| Beta vs total-return benchmark | {_num_text(comparison.beta)} |",
        (
            "| Max-drawdown difference (strategy - benchmark) | "
            f"{_pct_text(comparison.max_drawdown_difference)} |"
        ),
        f"| Closed trade count | {comparison.trade_count:,} |",
        f"| Annualized gross turnover | {_pct_text(comparison.annualized_gross_turnover)} |",
        f"| Average holding days (calendar) | {_num_text(comparison.average_holding_days, 1)} |",
        "",
        "## 三、組合層（附表）",
        "",
        "| Metric | Strategy | Total-return benchmark |",
        "|---|---:|---:|",
        (
            f"| CAGR | {_pct_text(comparison.strategy_path.cagr)} | "
            f"{_pct_text(comparison.benchmark_path.cagr)} |"
        ),
        (
            f"| MaxDD | {_pct_text(comparison.strategy_path.max_drawdown)} | "
            f"{_pct_text(comparison.benchmark_path.max_drawdown)} |"
        ),
        (
            "| Sharpe (daily, rf=0, sqrt(252)) | "
            f"{_num_text(comparison.strategy_path.sharpe)} | "
            f"{_num_text(comparison.benchmark_path.sharpe)} |"
        ),
        "",
        "## 判讀原則",
        "",
        BENCHMARK_INTERPRETATION_TW,
    ]
