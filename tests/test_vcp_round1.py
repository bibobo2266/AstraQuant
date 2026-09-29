from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from astraquant.data.market_coordinates import PriceUse, SignalPriceSemantics
from astraquant.execution.assumptions import (
    FixedBpsSlippage,
    SideAwareBpsFeeModel,
)
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import (
    ExecutionAvailability,
    ExecutionPriceDecision,
    RawExecutionBar,
    TradabilityState,
)
from astraquant.execution.service import SignalDeclaration
from astraquant.portfolio.policy import PortfolioPolicyConfig
from astraquant.research.exit_engine import ExitCompiler
from astraquant.research.feature_cache import FeatureCache
from astraquant.research.signal_engine import SignalContext
from astraquant.research.strategy_config import ComponentSpec, ExitConfig, ExitRuleConfig
from astraquant.research.technical_components import vcp_three_segment_details
from astraquant.research.vcp_round1 import (
    VCPRound1ExecutionSettings,
    VCPRound1ExitSettings,
    VCPRound1TradeRunner,
    build_adjusted_exit_features,
    close_exit_reason,
    compile_round1_exit_settings,
    update_atr_trail,
)


def _vcp_panel() -> pd.DataFrame:
    n = 70
    dates = pd.bdate_range("2020-01-02", periods=n)
    high = np.full(n, 100.0)
    low = np.full(n, 99.0)
    close = np.full(n, 99.0)
    volume = np.full(n, 1000.0)
    amount = np.full(n, 30_000_000.0)

    # Signal row index 60, prior base_len=30 is 30..59.
    high[30:40], low[30:40] = 100.0, 80.0
    high[40:50], low[40:50] = 100.0, 90.0
    high[50:60], low[50:60] = 100.0, 95.0
    volume[55:60] = 500.0
    close[59] = 99.0
    close[60] = 101.0
    high[60], low[60] = 102.0, 99.0
    volume[60] = 2000.0

    return pd.DataFrame(
        {
            "date": dates,
            "stock_id": ["2330"] * n,
            "open": close,
            "max": high,
            "min": low,
            "close": close,
            "Trading_Volume": volume,
            "Trading_money": amount,
            "observed_trade": True,
            "valid_ohlc": True,
        }
    )


def test_vcp_three_segment_exact_split_and_prior_only_denominators():
    panel = _vcp_panel()
    spec = ComponentSpec(
        type="VCP_THREE_SEGMENT",
        params={
            "base_len": 30,
            "contraction_ratio": 0.75,
            "last_contraction": 0.08,
            "dry_up": 0.65,
            "dry_up_window": 5,
            "breakout_volume_lookback": 50,
            "breakout_vol": 1.5,
            "liquidity_lookback": 20,
            "min_prior_avg_amount_twd": 20_000_000,
        },
    )
    details = vcp_three_segment_details(
        panel=panel,
        spec=spec,
        cache=FeatureCache(),
        context=SignalContext(source_revision="fixture"),
    )
    row = details.iloc[60]
    assert row["amplitude_1"] == pytest.approx(0.20)
    assert row["amplitude_2"] == pytest.approx(0.10)
    assert row["amplitude_3"] == pytest.approx(0.05)
    assert row["pivot_adjusted"] == pytest.approx(100.0)
    assert bool(row["signal"])

    # Breakout-day volume is numerator only. It must not enter either prior mean.
    before = float(row["dry_up_ratio"])
    changed = panel.copy()
    changed.loc[60, "Trading_Volume"] = 20_000.0
    row2 = vcp_three_segment_details(
        panel=changed,
        spec=spec,
        cache=FeatureCache(),
        context=SignalContext(source_revision="fixture-2"),
    ).iloc[60]
    assert float(row2["dry_up_ratio"]) == pytest.approx(before)
    assert float(row2["breakout_volume_ratio"]) > float(
        row["breakout_volume_ratio"]
    )


def test_wilder_atr_seed_is_simple_average_and_trail_never_moves_down():
    n = 25
    panel = pd.DataFrame(
        {
            "date": pd.bdate_range("2020-01-02", periods=n),
            "stock_id": ["2330"] * n,
            "max": np.arange(101.0, 101.0 + n),
            "min": np.arange(99.0, 99.0 + n),
            "close": np.arange(100.0, 100.0 + n),
        }
    )
    f = build_adjusted_exit_features(
        panel,
        atr_period=21,
        ma_window=21,
        end=panel["date"].iloc[-1],
    )
    assert np.isnan(f.loc[19, "atr"])
    assert f.loc[20, "atr"] == pytest.approx(2.0)

    first = update_atr_trail(
        None, high_watermark=110.0, atr=2.0, multiplier=2.5
    )
    widened_candidate = update_atr_trail(
        first, high_watermark=110.0, atr=5.0, multiplier=2.5
    )
    assert widened_candidate == pytest.approx(first)


def test_round1_exit_plan_has_no_legacy_stop_or_time_exit():
    cfg = ExitConfig(
        name="round1",
        rules=(
            ExitRuleConfig(
                type="ATR_TRAILING",
                params={
                    "period": 21,
                    "multiplier": 2.5,
                    "smoothing": "WILDER",
                    "trigger_field": "CLOSE",
                    "execution": "NEXT_OPEN",
                },
            ),
            ExitRuleConfig(
                type="MA_BREAK",
                params={
                    "window": 21,
                    "average": "SMA",
                    "require_cross": False,
                    "trigger_field": "CLOSE",
                    "execution": "NEXT_OPEN",
                },
            ),
        ),
    )
    plan = ExitCompiler().compile(cfg)
    parsed = compile_round1_exit_settings(plan)
    assert plan.stop_fraction is None
    assert plan.max_hold_sessions is None
    assert parsed.atr_period == 21
    policy = plan.apply_to_policy(
        PortfolioPolicyConfig(position_fraction=0.1, max_positions=10)
    )
    assert policy.stop_fraction is None
    assert policy.max_hold_sessions is None


class _FakeMarketData:
    def __init__(self, prices: dict[tuple[str, date, str], float]):
        self.prices = prices

    def resolve(self, *, ticker, session_date, side, use, field):
        day = pd.Timestamp(session_date).date()
        price = self.prices.get((str(ticker), day, field))
        if price is None:
            return ExecutionPriceDecision(
                availability=ExecutionAvailability.NOT_EXECUTABLE,
                use=use,
                side=str(side).lower(),
                field=field,
                price=None,
                reason="FIXTURE_MISSING",
                bar=None,
                tradability=None,
            )
        bar = RawExecutionBar(
            ticker=str(ticker),
            session_date=day,
            open=float(self.prices.get((str(ticker), day, "open"), price)),
            high=float(self.prices.get((str(ticker), day, "high"), price)),
            low=float(self.prices.get((str(ticker), day, "low"), price)),
            close=float(self.prices.get((str(ticker), day, "close"), price)),
        )
        trad = TradabilityState(
            ticker=str(ticker),
            session_date=day,
            observed_trade=True,
            valid_ohlc=True,
            buy_blocked=False,
            sell_blocked=False,
            reason="OBSERVED",
        )
        return ExecutionPriceDecision(
            availability=ExecutionAvailability.EXECUTABLE,
            use=use,
            side=str(side).lower(),
            field=field,
            price=float(price),
            reason="OK",
            bar=bar,
            tradability=trad,
        )


def _runner(*, sessions, market, exit_features):
    return VCPRound1TradeRunner(
        market_data=market,
        fill_factory=ExecutionFillFactory(
            fee_model=SideAwareBpsFeeModel(
                buy_bps=14.25,
                sell_bps=44.25,
            ),
            slippage_model=FixedBpsSlippage(bps=10),
        ),
        signal=SignalDeclaration(
            source="TEST:VCP_ROUND1",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        sessions=sessions,
        adjusted_exit_features=exit_features,
        corporate_actions=(),
        exit_settings=VCPRound1ExitSettings(
            atr_period=21,
            atr_multiplier=2.5,
            ma_window=21,
        ),
        execution_settings=VCPRound1ExecutionSettings(
            chase_multiple=1.05,
            normalized_initial_notional=1.0,
            settlement_lag_sessions=2,
            adjustment_method=(
                "ADJUSTED_RESEARCH_INDICATORS_RAW_EXECUTION_CA_ACCOUNTING"
            ),
        ),
    )


def test_next_day_gap_over_chase_limit_creates_no_entry():
    sessions = [date(2020, 1, 2), date(2020, 1, 3)]
    prices = {
        ("2330", sessions[0], "close"): 100.0,
        ("2330", sessions[0], "open"): 100.0,
        ("2330", sessions[0], "high"): 100.0,
        ("2330", sessions[0], "low"): 100.0,
        ("2330", sessions[1], "open"): 110.0,
        ("2330", sessions[1], "high"): 110.0,
        ("2330", sessions[1], "low"): 110.0,
        ("2330", sessions[1], "close"): 110.0,
    }
    runner = _runner(
        sessions=sessions,
        market=_FakeMarketData(prices),
        exit_features=pd.DataFrame(
            columns=[
                "date",
                "stock_id",
                "adjusted_high",
                "adjusted_close",
                "atr",
                "d_ma",
            ]
        ),
    )
    out = runner.simulate_config(
        config_id="c1",
        candidates=pd.DataFrame(
            [
                {
                    "signal_date": sessions[0],
                    "stock_id": "2330",
                    "pivot_adjusted": 100.0,
                    "adjusted_signal_close": 100.0,
                }
            ]
        ),
    )
    assert out.entry_count == 0
    assert out.chase_reject_count == 1
    assert out.trades.empty


def test_close_exit_executes_next_open_and_cost_is_not_double_counted():
    sessions = [
        date(2020, 1, 2),
        date(2020, 1, 3),
        date(2020, 1, 6),
    ]
    prices = {}
    for day in sessions:
        for field in ("open", "high", "low", "close"):
            prices[("2330", day, field)] = 100.0
    features = pd.DataFrame(
        [
            {
                "date": sessions[1],
                "stock_id": "2330",
                "adjusted_high": 100.0,
                "adjusted_close": 90.0,
                "atr": np.nan,
                "d_ma": 95.0,
            }
        ]
    )
    runner = _runner(
        sessions=sessions,
        market=_FakeMarketData(prices),
        exit_features=features,
    )
    candidates = pd.DataFrame(
        [
            {
                "signal_date": sessions[0],
                "stock_id": "2330",
                "pivot_adjusted": 100.0,
                "adjusted_signal_close": 100.0,
            }
        ]
    )
    out = runner.simulate_config(config_id="c1", candidates=candidates)
    assert out.entry_count == 1
    assert len(out.trades) == 1
    trade = out.trades.iloc[0]
    assert trade["entry_date"] == sessions[1].isoformat()
    assert trade["exit_date"] == sessions[2].isoformat()
    assert trade["exit_reason"] == "D21"

    entry_price = 100.0 * 1.001
    exit_price = 100.0 * 0.999
    q = float(trade["entry_investment"]) / (
        entry_price * (1 + 14.25 / 10_000)
    )
    expected = (
        q * exit_price * (1 - 44.25 / 10_000)
        - float(trade["entry_investment"])
    ) / float(trade["entry_investment"])
    assert float(trade["net_return"]) == pytest.approx(expected)


def test_period_end_open_position_is_not_forced_closed():
    sessions = [date(2020, 1, 2), date(2020, 1, 3)]
    prices = {}
    for day in sessions:
        for field in ("open", "high", "low", "close"):
            prices[("2330", day, field)] = 100.0
    features = pd.DataFrame(
        [
            {
                "date": sessions[1],
                "stock_id": "2330",
                "adjusted_high": 100.0,
                "adjusted_close": 100.0,
                "atr": np.nan,
                "d_ma": np.nan,
            }
        ]
    )
    runner = _runner(
        sessions=sessions,
        market=_FakeMarketData(prices),
        exit_features=features,
    )
    out = runner.simulate_config(
        config_id="c1",
        candidates=pd.DataFrame(
            [
                {
                    "signal_date": sessions[0],
                    "stock_id": "2330",
                    "pivot_adjusted": 100.0,
                    "adjusted_signal_close": 100.0,
                }
            ]
        ),
    )
    assert out.trades.empty
    assert len(out.open_positions) == 1
    assert out.open_positions.iloc[0]["pending_exit_state"] == "NONE"


def test_constant_adjusted_series_does_not_create_mechanical_exit():
    assert close_exit_reason(close=100.0, atr_trail=95.0, d_ma=100.0) is None
