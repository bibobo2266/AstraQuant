import pytest
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


def test_terminal_merger_carries_last_raw_then_extinguishes_and_pays(tmp_path):
    from astraquant.portfolio.corporate_actions import (
        CashEntitlementBasis,
        CorporateActionEvent,
        CorporateActionType,
    )
    from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction
    from astraquant.portfolio.models import Fill

    root = tmp_path / "terminal_source"
    (root / "raw").mkdir(parents=True)
    (root / "reference").mkdir(parents=True)

    pd.DataFrame([{
        "date": "2022-04-26",
        "stock_id": "4141",
        "open": 26.10,
        "max": 26.15,
        "min": 26.10,
        "close": 26.10,
    }]).to_parquet(root / "raw" / "prices_raw_2022.parquet", index=False)

    pd.DataFrame([{
        "date": "2022-04-26",
        "stock_id": "4141",
        "observed_trade": True,
        "valid_ohlc": True,
        "buy_blocked": False,
        "sell_blocked": False,
        "reason": "OBSERVED",
    }]).to_parquet(root / "reference" / "tradability.parquet", index=False)

    portfolio = PortfolioEngine(opening_cash=0.0)
    portfolio.positions.apply_fill(
        Fill(
            fill_id="seed-4141",
            order_id="seed-order-4141",
            ticker="4141",
            side="buy",
            quantity=1000,
            price=26.0,
            filled_at=datetime(2022, 4, 25),
        )
    )
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
            max_positions=1,
            stop_fraction=0.12,
            reentry_gap_sessions=20,
            max_hold_sessions=250,
            lot_size=1000,
            random_seed=1,
        )
    )
    policy.register_entry(
        ticker="4141",
        quantity=1000,
        fill_price=26.0,
        session_index=0,
    )
    sim = CanonicalStrategySimulator(
        execution=execution,
        portfolio=portfolio,
        policy=policy,
        signal=SignalDeclaration(
            source="terminal test",
            price_semantics=SignalPriceSemantics.SCALE_SENSITIVE,
        ),
        config=StrategySimulationConfig(settlement_lag_sessions=1),
    )

    event = CorporateActionEvent(
        event_id="MERGER-4141",
        ticker="4141",
        event_type=CorporateActionType.MERGER,
        effective_at=datetime(2022, 5, 3),
        known_at=datetime(2022, 3, 30, 18, 31, 29),
        payment_at=datetime(2022, 5, 10),
        cash_per_share=26.23,
        source="MOPS/TWSE",
    )
    sessions = [
        date(2022, 4, 26),
        date(2022, 4, 27),
        date(2022, 4, 28),
        date(2022, 4, 29),
        date(2022, 5, 2),
        date(2022, 5, 3),
        date(2022, 5, 4),
        date(2022, 5, 5),
        date(2022, 5, 6),
        date(2022, 5, 9),
        date(2022, 5, 10),
    ]

    result = sim.run(
        sessions=sessions,
        signals=pd.DataFrame(columns=["signal_date", "stock_id"]),
        corporate_actions=[
            HistoricalCorporateActionInstruction(
                event=event,
                applied_at=event.effective_at,
                component="MERGER_CASHOUT",
                cash_share_basis_mode=CashEntitlementBasis.OPENING_POSITION,
                terminal_stale_from=date(2022, 4, 27),
                extinguish_position=True,
            )
        ],
    )

    assert result.total_corporate_actions == 1
    assert result.total_corporate_cash_payments == 1
    assert portfolio.positions.positions["4141"].quantity == 0
    assert "4141" not in policy.managed_positions
    assert portfolio.cash.pending_receivables == 0.0
    assert portfolio.cash.settled_cash == 26230.0
    assert result.sessions[1].snapshot.valuation.nav == 26100.0
    assert result.sessions[5].snapshot.valuation.nav == 26230.0


def test_ca_transformed_mark_handles_invalid_ohlc_on_event_day(tmp_path):
    from astraquant.portfolio.corporate_actions import (
        CorporateActionEvent,
        CorporateActionType,
    )
    from astraquant.portfolio.historical_runner import HistoricalCorporateActionInstruction

    sim, portfolio, _ = _simulator(tmp_path)

    raw_path = sim.execution.market_data.source.root / "raw" / "prices_raw_2026.parquet"
    raw = pd.read_parquet(raw_path)
    mask = (
        raw["stock_id"].astype(str).eq("2330")
        & pd.to_datetime(raw["date"]).eq(pd.Timestamp("2026-01-06"))
    )
    raw.loc[mask, "max"] = 80.0
    raw.to_parquet(raw_path, index=False)

    trad_path = sim.execution.market_data.source.root / "reference" / "tradability.parquet"
    trad = pd.read_parquet(trad_path)
    tmask = (
        trad["stock_id"].astype(str).eq("2330")
        & pd.to_datetime(trad["date"]).eq(pd.Timestamp("2026-01-06"))
    )
    trad.loc[tmask, "valid_ohlc"] = False
    trad.loc[tmask, "buy_blocked"] = True
    trad.loc[tmask, "sell_blocked"] = True
    trad.loc[tmask, "reason"] = "INVALID_OHLC"
    trad.to_parquet(trad_path, index=False)

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
        event_id="STOCK-DIV-2330",
        ticker="2330",
        event_type=CorporateActionType.STOCK_DIVIDEND,
        effective_at=datetime(2026, 1, 6),
        share_multiplier=1.1,
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

    day = result.sessions[2]
    pos = next(x for x in day.snapshot.valuation.positions if x.ticker == "2330")
    assert pos.raw_mark == pytest.approx(102.0 / 1.1)
    assert pos.market_value == pytest.approx(2000.0 * 102.0)
