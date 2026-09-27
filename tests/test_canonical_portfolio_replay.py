from datetime import date, datetime

import pandas as pd

from astraquant.data.market_coordinates import PriceUse, SignalPriceSemantics
from astraquant.data.source_adapter import SourceDataAdapter
from astraquant.execution.assumptions import FixedBpsSlippage, ZeroFeeModel
from astraquant.execution.fills import ExecutionFillFactory
from astraquant.execution.market_data import ExecutionMarketData
from astraquant.execution.service import CanonicalExecutionService, SignalDeclaration
from astraquant.portfolio.corporate_actions import CorporateActionEvent, CorporateActionType
from astraquant.portfolio.engine import PortfolioEngine
from astraquant.portfolio.models import OrderIntent
from astraquant.portfolio.replay_runner import CanonicalPortfolioReplay


def _build_replay(tmp_path):
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
    return CanonicalPortfolioReplay(execution=execution, portfolio=portfolio), portfolio


def test_event_driven_replay_handles_trade_split_dividend_and_nav(tmp_path):
    replay, portfolio = _build_replay(tmp_path)
    signal = SignalDeclaration(
        source="declared test signal",
        price_semantics=SignalPriceSemantics.SCALE_INVARIANT,
    )

    entry_at = datetime(2026, 1, 2, 9, 0)
    replay.execute_trade(
        intent=OrderIntent(
            intent_id="I-BUY",
            ticker="2330",
            side="buy",
            quantity=100,
            created_at=entry_at,
            rationale="test",
        ),
        signal=signal,
        order_id="O-BUY",
        fill_id="F-BUY",
        submitted_at=entry_at,
        session_date=date(2026, 1, 2),
        use=PriceUse.ENTRY,
        field="open",
        settlement_id="S-BUY",
        settlement_due=datetime(2026, 1, 4),
    )
    replay.settle("S-BUY", datetime(2026, 1, 4))

    replay.apply_share_mutation(
        event=CorporateActionEvent(
            event_id="CA-SPLIT",
            ticker="2330",
            event_type=CorporateActionType.SPLIT,
            effective_at=datetime(2026, 1, 5),
            share_multiplier=2.0,
            source="official",
        ),
        applied_at=datetime(2026, 1, 5),
    )

    replay.accrue_cash_dividend(
        event=CorporateActionEvent(
            event_id="CA-DIV",
            ticker="2330",
            event_type=CorporateActionType.CASH_DIVIDEND,
            effective_at=datetime(2026, 1, 5),
            payment_at=None,
            cash_per_share=1.0,
            source="official",
        ),
        accrued_at=datetime(2026, 1, 5),
    )

    mid = replay.snapshot(at=datetime(2026, 1, 5))
    pos = portfolio.positions.positions["2330"]

    assert pos.quantity == 200
    assert pos.avg_cost == 50
    assert portfolio.cash.settled_cash == 40000
    assert portfolio.cash.pending_receivables == 200
    assert mid.valuation.market_value == 11000
    assert mid.valuation.nav == 51200

    exit_at = datetime(2026, 1, 6, 13, 30)
    replay.execute_trade(
        intent=OrderIntent(
            intent_id="I-SELL",
            ticker="2330",
            side="sell",
            quantity=200,
            created_at=exit_at,
            rationale="test",
        ),
        signal=signal,
        order_id="O-SELL",
        fill_id="F-SELL",
        submitted_at=exit_at,
        session_date=date(2026, 1, 6),
        use=PriceUse.EXIT,
        field="close",
        settlement_id="S-SELL",
        settlement_due=datetime(2026, 1, 8),
    )
    replay.settle("S-SELL", datetime(2026, 1, 8))

    final = replay.snapshot(at=datetime(2026, 1, 6))

    assert portfolio.positions.positions["2330"].quantity == 0
    assert portfolio.cash.settled_cash == 52000
    assert portfolio.cash.pending_receivables == 200
    assert final.valuation.market_value == 0
    assert final.valuation.nav == 52200


def test_replay_requires_shared_portfolio_instance(tmp_path):
    replay, _ = _build_replay(tmp_path)
    other = PortfolioEngine(opening_cash=1.0)

    try:
        CanonicalPortfolioReplay(execution=replay.execution, portfolio=other)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "share one PortfolioEngine" in str(exc)
