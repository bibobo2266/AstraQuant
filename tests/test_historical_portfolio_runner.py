from datetime import date, datetime

import pandas as pd
import pytest

from astraquant.data.market_coordinates import PriceUse, SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.historical_runner import (
    HistoricalCorporateActionInstruction,
    HistoricalPortfolioRunner,
    HistoricalReplayError,
    HistoricalTradeInstruction,
)
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay


def _runner(tmp_path):
    root = tmp_path / "source"
    (root / "raw").mkdir(parents=True)
    (root / "reference").mkdir(parents=True)

    pd.DataFrame([
        {"date": "2026-01-02", "stock_id": "2330", "open": 100.0, "max": 105.0, "min": 95.0, "close": 102.0},
        {"date": "2026-01-05", "stock_id": "2330", "open": 52.0, "max": 56.0, "min": 50.0, "close": 55.0},
        {"date": "2026-01-06", "stock_id": "2330", "open": 58.0, "max": 62.0, "min": 57.0, "close": 60.0},
    ]).to_parquet(root / "raw" / "prices_raw_2026.parquet", index=False)

    pd.DataFrame([
        {
            "date": d,
            "stock_id": "2330",
            "observed_trade": True,
            "valid_ohlc": True,
            "buy_blocked": False,
            "sell_blocked": False,
            "reason": "OBSERVED",
        }
        for d in ["2026-01-02", "2026-01-05", "2026-01-06"]
    ]).to_parquet(root / "reference" / "tradability.parquet", index=False)

    portfolio = PortfolioEngine(opening_cash=50000.0)
    execution = CanonicalExecutionService(
        market_data=ExecutionMarketData(SourceDataAdapter(root)),
        fill_factory=ExecutionFillFactory(
            fee_model=ZeroFeeModel(),
            slippage_model=FixedBpsSlippage(bps=0),
        ),
        portfolio=portfolio,
    )
    replay = CanonicalPortfolioReplay(execution=execution, portfolio=portfolio)
    return HistoricalPortfolioRunner(replay), portfolio


def _signal():
    return SignalDeclaration(
        source="historical-runner-test",
        price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )


def test_historical_runner_processes_sessions_in_order(tmp_path):
    runner, portfolio = _runner(tmp_path)

    buy = HistoricalTradeInstruction(
        intent=OrderIntent(
            intent_id="I1",
            ticker="2330",
            side="buy",
            quantity=100,
            created_at=datetime(2026, 1, 2, 9, 0),
            rationale="test",
        ),
        signal=_signal(),
        order_id="O1",
        fill_id="F1",
        submitted_at=datetime(2026, 1, 2, 9, 0),
        session_date=date(2026, 1, 2),
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="S1",
        settlement_due=datetime(2026, 1, 5, 0, 0),
    )
    split = HistoricalCorporateActionInstruction(
        event=CorporateActionEvent(
            event_id="CA1",
            ticker="2330",
            event_type=CorporateActionType.SPLIT,
            effective_at=datetime(2026, 1, 5),
            share_multiplier=2.0,
            source="official",
        ),
        applied_at=datetime(2026, 1, 5),
    )
    sell = HistoricalTradeInstruction(
        intent=OrderIntent(
            intent_id="I2",
            ticker="2330",
            side="sell",
            quantity=200,
            created_at=datetime(2026, 1, 6, 13, 0),
            rationale="test",
        ),
        signal=_signal(),
        order_id="O2",
        fill_id="F2",
        submitted_at=datetime(2026, 1, 6, 13, 0),
        session_date=date(2026, 1, 6),
        use=PriceUse.EXIT,
        field="close",
        settlement_id="S2",
        settlement_due=datetime(2026, 1, 6, 0, 0),
    )

    result = runner.run(
        sessions=[date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)],
        trades=[buy, sell],
        corporate_actions=[split],
    )

    assert result.total_trades == 2
    assert result.total_corporate_actions == 1
    assert result.total_settlements == 1
    assert portfolio.positions.positions["2330"].quantity == 0
    assert portfolio.cash.pending_receivables == 12000
    assert result.sessions[-1].snapshot.valuation.market_value == 0


def test_historical_runner_accrues_dividend_on_opening_holdings(tmp_path):
    runner, portfolio = _runner(tmp_path)

    buy = HistoricalTradeInstruction(
        intent=OrderIntent(
            intent_id="I1",
            ticker="2330",
            side="buy",
            quantity=100,
            created_at=datetime(2026, 1, 2, 9, 0),
            rationale="test",
        ),
        signal=_signal(),
        order_id="O1",
        fill_id="F1",
        submitted_at=datetime(2026, 1, 2, 9, 0),
        session_date=date(2026, 1, 2),
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="S1",
        settlement_due=datetime(2026, 1, 5),
    )
    dividend = HistoricalCorporateActionInstruction(
        event=CorporateActionEvent(
            event_id="DIV1",
            ticker="2330",
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=datetime(2026, 1, 5),
            cash_per_share=2.0,
        ),
        applied_at=datetime(2026, 1, 5),
    )

    result = runner.run(
        sessions=[date(2026, 1, 2), date(2026, 1, 5)],
        trades=[buy],
        corporate_actions=[dividend],
    )

    assert result.total_corporate_actions == 1
    assert portfolio.cash.pending_receivables == 200


def test_historical_runner_rejects_instruction_outside_calendar(tmp_path):
    runner, _ = _runner(tmp_path)
    trade = HistoricalTradeInstruction(
        intent=OrderIntent(
            intent_id="I1",
            ticker="2330",
            side="buy",
            quantity=10,
            created_at=datetime(2026, 1, 2, 9, 0),
            rationale="test",
        ),
        signal=_signal(),
        order_id="O1",
        fill_id="F1",
        submitted_at=datetime(2026, 1, 2, 9, 0),
        session_date=date(2026, 1, 2),
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="S1",
        settlement_due=datetime(2026, 1, 5),
    )

    with pytest.raises(HistoricalReplayError, match="outside session calendar"):
        runner.run(
            sessions=[date(2026, 1, 5)],
            trades=[trade],
        )


def test_non_session_corporate_action_maps_to_next_session(tmp_path):
    runner, portfolio = _runner(tmp_path)

    buy = HistoricalTradeInstruction(
        intent=OrderIntent(
            intent_id="I1",
            ticker="2330",
            side="buy",
            quantity=100,
            created_at=datetime(2026, 1, 2, 9, 0),
            rationale="test",
        ),
        signal=_signal(),
        order_id="O1",
        fill_id="F1",
        submitted_at=datetime(2026, 1, 2, 9, 0),
        session_date=date(2026, 1, 2),
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="S1",
        settlement_due=datetime(2026, 1, 5),
    )
    weekend_dividend = HistoricalCorporateActionInstruction(
        event=CorporateActionEvent(
            event_id="DIV-WEEKEND",
            ticker="2330",
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=datetime(2026, 1, 3),
            cash_per_share=2.0,
        ),
        applied_at=datetime(2026, 1, 3),
    )

    result = runner.run(
        sessions=[date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)],
        trades=[buy],
        corporate_actions=[weekend_dividend],
    )

    day2 = result.sessions[1]
    assert day2.session_date == date(2026, 1, 5)
    assert day2.corporate_actions_applied == 1
    assert portfolio.cash.pending_receivables == 200


def test_corporate_action_after_calendar_horizon_fails(tmp_path):
    runner, _ = _runner(tmp_path)
    event = HistoricalCorporateActionInstruction(
        event=CorporateActionEvent(
            event_id="DIV-AFTER",
            ticker="2330",
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=datetime(2026, 1, 7),
            cash_per_share=2.0,
        ),
        applied_at=datetime(2026, 1, 7),
    )

    from astraquant.portfolio.calendar import CalendarMappingError
    with pytest.raises(CalendarMappingError, match="no trading session"):
        runner.run(
            sessions=[date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)],
            corporate_actions=[event],
        )
