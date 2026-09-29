import pandas as pd
import pytest

from astraquant.portfolio.models import Fill
from astraquant.portfolio.performance_reporting import TradeReport, TradeStatistics
from astraquant.portfolio.trade_reconstruction import TradeReconstructionResult
from astraquant.research.benchmark import (
    build_buy_hold_benchmark_nav,
    compare_strategy_to_total_return_benchmark,
)


def _trade_report():
    return TradeReport(
        reconstruction=TradeReconstructionResult(closed_lots=(), open_lots=()),
        closed_trades=(),
        statistics=TradeStatistics(
            n=2,
            win_rate=0.5,
            average_win=0.1,
            average_loss=-0.05,
            payoff_ratio=2.0,
            expectancy=0.025,
            average_holding_days=20.0,
        ),
    )


def test_buy_hold_benchmark_uses_exact_strategy_dates_and_initial_cash():
    dates = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
    tri = pd.Series([100.0, 105.0, 110.0], index=dates)
    nav = build_buy_hold_benchmark_nav(
        tri,
        strategy_dates=dates,
        initial_cash=1_000_000.0,
    )
    assert nav.iloc[0] == 1_000_000.0
    assert nav.iloc[-1] == 1_100_000.0


def test_benchmark_hard_fails_when_strategy_session_is_missing():
    tri = pd.Series(
        [100.0, 105.0],
        index=pd.to_datetime(["2026-01-02", "2026-01-06"]),
    )
    with pytest.raises(ValueError, match="missing strategy trading dates"):
        build_buy_hold_benchmark_nav(
            tri,
            strategy_dates=pd.to_datetime(
                ["2026-01-02", "2026-01-05", "2026-01-06"]
            ),
            initial_cash=1_000_000.0,
        )


def test_comparison_reports_excess_beta_drawdown_and_turnover():
    dates = pd.to_datetime(
        ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    )
    strategy = pd.Series(
        [1_000_000.0, 1_020_000.0, 1_010_000.0, 1_060_000.0],
        index=dates,
    )
    tri = pd.Series([100.0, 101.0, 100.5, 103.0], index=dates)
    fills = [
        Fill(
            fill_id="b",
            order_id="ob",
            ticker="2330",
            side="buy",
            quantity=1000,
            price=100.0,
            filled_at=pd.Timestamp("2026-01-05").to_pydatetime(),
        ),
        Fill(
            fill_id="s",
            order_id="os",
            ticker="2330",
            side="sell",
            quantity=1000,
            price=106.0,
            filled_at=pd.Timestamp("2026-01-07").to_pydatetime(),
        ),
    ]
    out = compare_strategy_to_total_return_benchmark(
        strategy_nav=strategy,
        total_return_index=tri,
        initial_cash=1_000_000.0,
        fills=fills,
        trade_report=_trade_report(),
    )
    assert out.cumulative_excess_return == pytest.approx(0.03)
    assert out.trade_count == 2
    assert out.average_holding_days == 20.0
    assert out.annualized_gross_turnover > 0
    assert -1 <= out.daily_return_correlation <= 1
