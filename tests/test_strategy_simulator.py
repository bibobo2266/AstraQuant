from datetime import date, datetime

import pandas as pd

from astraquant.data.market_coordinates import SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.policy import PortfolioIntentPolicy, PortfolioPolicyConfig
from astraquant.portfolio.strategy_simulator import (
    CanonicalStrategySimulator,
    StrategySimulationConfig,
)


def _simulator(tmp_path, *, max_positions=1, max_hold=250):
    root = tmp_path / "source"
    (root / "raw").mkdir(parents=True)
    (root / "reference").mkdir(parents=True)

    rows = []
    specs = {
        "2330": [
            ("2026-01-02", 100.0, 102.0, 99.0, 101.0),
            ("2026-01-05", 100.0, 103.0, 95.0, 102.0),
            ("2026-01-06", 85.0, 90.0, 80.0, 88.0),
            ("2026-01-07", 90.0, 92.0, 89.0, 91.0),
        ],
        "2317": [
            ("2026-01-02", 50.0, 51.0, 49.0, 50.0),
            ("2026-01-05", 50.0, 52.0, 49.0, 51.0),
            ("2026-01-06", 52.0, 54.0, 51.0, 53.0),
            ("2026-01-07", 53.0, 55.0, 52.0, 54.0),
        ],
    }
    for ticker, values in specs.items():
        for d, o, h, l, c in values:
            rows.append(
                {
                    "date": d,
                    "stock_id": ticker,
                    "open": o,
                    "max": h,
                    "min": l,
                    "close": c,
                }
            )
    pd.DataFrame(rows).to_parquet(
        root / "raw" / "prices_raw_2026.parquet",
        index=False,
    )

    trad = []
    for ticker in specs:
        for d, *_ in specs[ticker]:
            trad.append(
                {
                    "date": d,
                    "stock_id": ticker,
                    "observed_trade": True,
                    "valid_ohlc": True,
                    "buy_blocked": False,
                    "sell_blocked": False,
                    "reason": "OBSERVED",
                }
            )
    pd.DataFrame(trad).to_parquet(
        root / "reference" / "tradability.parquet",
        index=False,
    )

    portfolio = PortfolioEngine(opening_cash=1_000_000.0)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(SourceDataAdapter(root)),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    policy = PortfolioIntentPolicy(
        PortfolioPolicyConfig(
            position_fraction=0.20,
            max_positions=max_positions,
            stop_fraction=0.12,
            reentry_gap_sessions=20,
            max_hold_sessions=max_hold,
            lot_size=1000,
            random_seed=1,
        )
    )
    sim = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=SignalDeclaration(
            source="canonical breakout test",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=1),
    )
    return sim, portfolio, policy


def test_strategy_simulator_enters_next_session_and_stops_on_raw(tmp_path):
    sim, portfolio, policy = _simulator(tmp_path)
    sessions = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    ]
    signals = pd.DataFrame(
        [{"signal_date": "2026-01-02", "stock_id": "2330"}]
    )

    result = sim.run(sessions=sessions, signals=signals)

    assert result.total_entries == 1
    assert result.total_stop_exits == 1
    assert result.total_max_hold_exits == 0
    assert portfolio.positions.positions["2330"].quantity == 0
    assert "2330" not in policy.managed_positions
    stop_order = portfolio.orders.orders["order:stop:2026-01-06:2330"]
    assert stop_order.fills[0].price == 85.0


def test_intraday_stop_does_not_free_same_open_capacity(tmp_path):
    sim, portfolio, policy = _simulator(tmp_path, max_positions=1)
    sessions = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    ]
    signals = pd.DataFrame(
        [
            {"signal_date": "2026-01-02", "stock_id": "2330"},
            {"signal_date": "2026-01-05", "stock_id": "2317"},
        ]
    )

    result = sim.run(sessions=sessions, signals=signals)

    day3 = result.sessions[2]
    assert day3.signals_for_open == 1
    assert day3.entries_executed == 0
    assert day3.entries_skipped == 1
    assert day3.stop_exits == 1
    assert "2317" not in portfolio.positions.positions or portfolio.positions.positions["2317"].quantity == 0
    assert "2330" not in policy.managed_positions


def test_max_hold_exit_uses_raw_close(tmp_path):
    sim, portfolio, policy = _simulator(tmp_path, max_hold=1)
    # Change 2330 day-3 low so stop is not triggered.
    market = sim.execution.market_data
    root = market.source.root
    raw_path = root / "raw" / "prices_raw_2026.parquet"
    raw = pd.read_parquet(raw_path)
    mask = (
        raw["stock_id"].astype(str).eq("2330")
        & pd.to_datetime(raw["date"]).eq(pd.Timestamp("2026-01-06"))
    )
    raw.loc[mask, "open"] = 102.0
    raw.loc[mask, "max"] = 106.0
    raw.loc[mask, "min"] = 100.0
    raw.loc[mask, "close"] = 105.0
    raw.to_parquet(raw_path, index=False)

    sessions = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    ]
    signals = pd.DataFrame(
        [{"signal_date": "2026-01-02", "stock_id": "2330"}]
    )

    result = sim.run(sessions=sessions, signals=signals)

    assert result.total_stop_exits == 0
    assert result.total_max_hold_exits == 1
    order = portfolio.orders.orders["order:maxhold:2026-01-06:2330"]
    assert order.fills[0].price == 105.0
    assert "2330" not in policy.managed_positions


def test_strategy_simulator_settles_dividend_on_payment_date(tmp_path):
    from astraquant.portfolio.corporate_actions import (
        CorporateActionEvent,
        CorporateActionType,
    )
    from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction

    sim, portfolio, _ = _simulator(tmp_path)
    sessions = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
    ]
    signals = pd.DataFrame(
        [{"signal_date": "2026-01-02", "stock_id": "2330"}]
    )
    event = CorporateActionEvent(
        event_id="DIV-PAY",
        ticker="2330",
        event_type=CorporateActionType.CASH_DIVIDEND,
        effective_at=datetime(2026, 1, 6),
        payment_at=datetime(2026, 1, 7),
        cash_per_share=1.0,
        source="test",
    )

    result = sim.run(
        sessions=sessions,
        signals=signals,
        corporate_actions=[
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
            )
        ],
    )

    assert result.total_corporate_actions == 1
    assert result.total_corporate_cash_payments == 1
    assert result.sessions[2].corporate_cash_payments == 0
    assert result.sessions[3].corporate_cash_payments == 1
    assert portfolio.cash.pending_receivables == 0.0
    assert "DIV-PAY" in portfolio.corporate_actions.completed_dividends
